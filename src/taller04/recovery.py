"""Recupera observations perdidas desde mediciones originales, con procedencia explícita.

No llama al modelo ni cambia respuestas/etiquetas. Conserva IDs y tokens; el inicio
se deriva del timestamp final y duración monotónica guardados por el testigo. La
jerarquía se reconstruye del cierre anidado de los roles y retriever instrumentados.
Después hay que exportar y verificar contra Langfuse: el testigo no es la entrega.
"""
from __future__ import annotations
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from .guardrails import mask
from .simulator import ROOT
from .telemetry_outbox import send


def build_payload(rows,existing_ids,version):
    payload=ExportTraceServiceRequest();resource=payload.resource_spans.add()
    scope=resource.scope_spans.add();scope.scope.name='langfuse-sdk';scope.scope.version='4.17.0'
    grouped=defaultdict(list)
    for r in rows:grouped[r['traza']].append(r)
    recovered=[]
    for trace,spans in grouped.items():
        root=next((s for s in spans if s['span']=='corrida'),None)
        if root is None:continue
        for i,r in enumerate(spans):
            if r['observation_id'] in existing_ids:continue
            parent=None
            if r['span']!='corrida':
                parent=root['observation_id']
                if r.get('agente') and r['span']!='agent':
                    node=next((s for s in spans[i+1:] if s['span']=='agent' and s['nombre']==r['agente']),None)
                    if node:parent=node['observation_id']
                if r['span']=='llm' and r['nombre']=='embeddings':
                    retriever=next((s for s in spans[i+1:] if s['span']=='retriever'),None)
                    if retriever:parent=retriever['observation_id']
            span=scope.spans.add();span.trace_id=bytes.fromhex(trace);span.span_id=bytes.fromhex(r['observation_id'])
            if parent:span.parent_span_id=bytes.fromhex(parent)
            span.name=r['nombre'];span.kind=1
            end=int(datetime.fromisoformat(r['timestamp']).timestamp()*1e9)
            span.end_time_unix_nano=end;span.start_time_unix_nano=end-int(r['duracion_ms']*1e6)
            def attr(key,value):
                a=span.attributes.add();a.key=key
                if isinstance(value,bool):a.value.bool_value=value
                elif isinstance(value,int):a.value.int_value=value
                elif isinstance(value,str):a.value.string_value=value
                else:a.value.string_value=json.dumps(mask(value),ensure_ascii=False,default=str)
            attr('langfuse.observation.type',{'corrida':'span','llm':'generation','herramienta':'tool'}.get(r['span'],r['span']))
            attr('session.id','taller04-'+version)
            attr('langfuse.observation.input',r.get('input'))
            attr('langfuse.observation.output',r.get('output'))
            attr('langfuse.observation.metadata',{'prompt_version':version,'agente':r.get('agente'),'recovered_from_witness':True,'timing_source':'end_timestamp_minus_measured_duration','hierarchy_source':'instrumented_nested_closure','result_bytes':r.get('result_bytes')})
            attr('langfuse.observation.version',version)
            if r['span']=='corrida':attr('langfuse.trace.name','IncidentCommander.run')
            if r['span']=='llm':
                attr('langfuse.observation.model.name',r.get('modelo','unknown'))
                attr('langfuse.observation.usage_details',{'input':r.get('tokens_entrada',0),'output':r.get('tokens_salida',0)})
                attr('langfuse.observation.cost_details',{'input':0,'output':0,'total':0})
            if r.get('error'):
                attr('langfuse.observation.level','ERROR');attr('langfuse.observation.status_message',r['error']);span.status.code=2
            recovered.append({'traza':trace,'observation_id':r['observation_id'],'span':r['span']})
    return payload.SerializeToString(),recovered


def recover(version):
    folder=ROOT/'reports'/version
    observations=[json.loads(l) for l in (folder/'spans.jsonl').read_text().splitlines()]
    existing={s['observation_id'] for s in observations if s.get('observation_id')}
    wanted={r['result']['traza_id'] for r in json.loads((folder/'runs.json').read_text())}
    witness=[json.loads(l) for l in (folder/f'witness_{version}.jsonl').read_text().splitlines()]
    rows=[r for r in witness if r['traza'] in wanted]
    data,recovered=build_payload(rows,existing,version)
    if recovered:
        pending=ROOT/'reports/otlp_pending';pending.mkdir(parents=True,exist_ok=True)
        path=pending/(hashlib.sha256(data).hexdigest()+'.otlp');path.write_bytes(data);send(path)
    (folder/'recuperacion_observaciones.json').write_text(json.dumps({'origen':'mediciones originales del testigo; no se regeneraron respuestas','observaciones':recovered},ensure_ascii=False,indent=2))
    return {'reenviadas':len(recovered),'requiere_exportar_y_verificar':True}
