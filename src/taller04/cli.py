from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from .simulator import ROOT

load_dotenv(ROOT/'.env')

def main():
    p=argparse.ArgumentParser(description='Taller04: operación Kubernetes simulada y LLMOps real')
    p.add_argument('command',choices=['recheck','recover','audit','drain','doctor','setup','index','run','evaluate','preflight','judge','calibrate','export','recheck','guardrails','part0','ragas','report'])
    p.add_argument('--version',choices=['v1','v2'],help='Por defecto v2 para operar (run); v1 para evaluación y exportación');p.add_argument('--question');p.add_argument('--limit',type=int);p.add_argument('--approve-restart',action='store_true',help='Aprobación externa explícita solo para payments/checkout-api en el simulador')
    a=p.parse_args()
    a.version=a.version or ('v2' if a.command=='run' else 'v1')
    from .evaluation import load_cases
    if a.command=='recover':
        from .recovery import recover
        print(recover(a.version))
    elif a.command=='audit':
        from .audit import audit
        print(json.dumps(audit(),ensure_ascii=False,indent=2))
    elif a.command=='drain':
        from .telemetry_outbox import drain
        print(drain())
    elif a.command=='doctor':
        from .models import ModelClient
        from .observability import Recorder
        from qdrant_client import QdrantClient
        print(json.dumps({'agent':ModelClient().validate(),'judge':ModelClient('judge').validate(),'langfuse':Recorder().lf.auth_check(),'qdrant':[c.name for c in QdrantClient(url=os.getenv('QDRANT_URL','http://localhost:6333')).get_collections().collections],'golden':len(load_cases())},indent=2))
    elif a.command=='setup':
        from .operations import PROMPT
        from .observability import Recorder
        lf=Recorder().lf
        if not lf.auth_check(): raise RuntimeError('Langfuse auth_check falló')
        try: prompt=lf.get_prompt('taller04-incident-commander',label='production')
        except Exception:
            prompt=lf.create_prompt(name='taller04-incident-commander',type='text',prompt=PROMPT,labels=['production'],commit_message='Contrato SRE basado en evidencia, abstención, citas y aprobación explícita.')
        print('Prompt registrado',prompt.version)
    elif a.command=='index':
        from .operations import Knowledge
        print(Knowledge().index())
    elif a.command=='run':
        from .operations import IncidentCommander
        if not a.question: p.error('--question requerido')
        print(json.dumps(IncidentCommander(version=a.version).run(a.question,approval={'approved':True,'namespace':'payments','deployment':'checkout-api'} if a.approve_restart else None),ensure_ascii=False,indent=2))
    elif a.command in ('evaluate','preflight','judge','calibrate','export','recheck'):
        from . import evaluation as ev
        f=getattr(ev,a.command)
        result=f(a.version,a.limit) if a.command=='evaluate' else f() if a.command=='preflight' else f(a.version)
        if a.command=='calibrate': print(json.dumps(result,ensure_ascii=False,indent=2))
    elif a.command=='guardrails':
        import importlib.util
        from .guardrails import validar_entrada,validar_salida
        from .evaluation import write_csv
        folder=ROOT/'referencia/Lab-04-LLMOps'
        def module(name):
            spec=importlib.util.spec_from_file_location(name,folder/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
        tester=module('probar_guardrails');old=module('guardrails')
        cases=json.loads((ROOT/'ataques.json').read_text())['casos']
        summary={}
        for name,entry,exit in [('propios',validar_entrada,validar_salida),('ejemplo',old.validate_input,old.validate_output)]:
            rows=tester.probar(cases,entry,exit);write_csv(ROOT/f'reports/guardrails_{name}.csv',rows);summary[name]=tester.resumen(rows)
        (ROOT/'reports/guardrails_resumen.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
    elif a.command=='part0':
        import subprocess,sys
        for case in ['ceros','guardrails','traza']:
            r=subprocess.run([sys.executable,'guion.py',case],cwd=ROOT/'referencia/Lab-04-LLMOps',capture_output=True,text=True)
            (ROOT/f'reports/parte0_{case}.txt').write_text(r.stdout+r.stderr)
            if r.returncode: raise RuntimeError(f'Parte0 {case} falló: {r.stderr}')
            print(case,'reproducido')
    elif a.command=='ragas':
        from .ragas_eval import run
        run(a.version)
    elif a.command=='report':
        from .reporting import build
        build()

if __name__=='__main__': main()
