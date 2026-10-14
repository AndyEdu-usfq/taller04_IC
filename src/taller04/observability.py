"""Langfuse obligatorio en vivo; testigo JSONL adicional, nunca sustituto del exportado."""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
import json
import time
import uuid
from .guardrails import mask

ACTIVE=ContextVar('taller04_recorder',default=None)
AGENT=ContextVar('taller04_agent',default=None)

class Recorder:
    def __init__(self, session='taller04-base', version='v1', offline=False, output=None):
        self.session=session; self.version=version; self.offline=offline
        self.output=Path(output or Path(__file__).resolve().parents[2]/'reports/witness.jsonl')
        self.rows=[]; self.lf=None
        if not offline:
            from langfuse import Langfuse
            from .telemetry_outbox import DurableExporter
            self.lf=Langfuse(mask=mask, timeout=30, span_exporter=DurableExporter())
    @contextmanager
    def span(self, kind, name, input=None, **metadata):
        started=time.perf_counter(); row={'span':kind,'nombre':name,'input':mask(input),'agente':AGENT.get(),'error':None,'prompt_version':self.version,**metadata}
        ctx=None; obs=None
        try:
            if self.lf:
                types={'corrida':'span','llm':'generation','herramienta':'tool'}
                ctx=self.lf.start_as_current_observation(name=name,as_type=types.get(kind,kind),input=mask(input),metadata={'prompt_version':self.version,**metadata})
                obs=ctx.__enter__()
                row['traza']=self.lf.get_current_trace_id(); row['observation_id']=obs.id
            else:
                row['traza']=getattr(self,'trace_id',None) or uuid.uuid4().hex
            if kind=='corrida': self.trace_id=row['traza']
            yield row
        except BaseException as exc:
            row['error']=str(mask(str(exc))); raise
        finally:
            row['duracion_ms']=round((time.perf_counter()-started)*1000,3)
            row['timestamp']=datetime.now(timezone.utc).isoformat()
            row['traza']=row.get('traza',getattr(self,'trace_id',None))
            if obs:
                kwargs={'output':mask(row.get('output')), 'metadata':{'prompt_version':self.version,'agente':row['agente'],'duracion_ms':row['duracion_ms'], 'result_bytes':row.get('result_bytes'), 'usage_available':row.get('usage_available', True)}}
                if kind=='llm':
                    kwargs.update(model=row.get('modelo'),usage_details={'input':row.get('tokens_entrada',0),'output':row.get('tokens_salida',0)},cost_details={'input':0,'output':0,'total':0})
                    if row.get('prompt') is not None: kwargs['prompt']=row['prompt']
                if row['error']: kwargs.update(level='ERROR',status_message=row['error'])
                obs.update(**kwargs); ctx.__exit__(None,None,None)
            row.pop('prompt',None)
            self.rows.append(mask(row))
            self.output.parent.mkdir(parents=True,exist_ok=True)
            with self.output.open('a') as f: f.write(json.dumps(mask(row),ensure_ascii=False,default=str)+'\n')
    @contextmanager
    def run(self, question):
        from contextlib import nullcontext
        if self.lf:
            from langfuse import propagate_attributes
        token=ACTIVE.set(self)
        try:
            with self.span('corrida','IncidentCommander.run',question) as root:
                with (propagate_attributes(session_id=self.session,tags=['taller-04','opcion-c'],metadata={'prompt_version':self.version}) if self.lf else nullcontext()):
                    yield root
        finally:
            ACTIVE.reset(token)
            if self.lf: self.lf.flush()
    def call(self, kind, name, fn, *args, **kwargs):
        with self.span(kind,name,{'args':args,'kwargs':kwargs}) as row:
            value=fn(*args,**kwargs); row['output']=mask(value)
            if kind=='herramienta': row['result_bytes']=len(json.dumps(value,default=str).encode())
            return value
    def node(self, name, fn):
        def wrapped(state):
            token=AGENT.set(name)
            try:
                with self.span('agent',name,state) as row:
                    value=fn(state); row['output']=value; return value
            finally: AGENT.reset(token)
        return wrapped
