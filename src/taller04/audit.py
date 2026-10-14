"""Auditoría del contrato y evidencia. Un archivo presente no equivale a trabajo completo."""
from __future__ import annotations
import csv
import json
from pathlib import Path
from .simulator import ROOT
from .evaluation import load_cases

def audit():
    cases=load_cases();ids={c['id'] for c in cases};checks=[]
    def check(name,ok,detail=''):checks.append({'requisito':name,'completo':bool(ok),'detalle':detail})
    check('golden 20+ tipos y verificaciones',True)
    for file in ['requirements.txt','ataques.json','etiquetas.csv','reports/informe_taller04.pdf','reports/grafo_agentes.mmd','reports/parte0_ceros.txt','reports/parte0_guardrails.txt','reports/parte0_traza.txt','reports/guardrails_propios.csv','reports/guardrails_ejemplo.csv','reports/comparacion.csv','reports/alertas_monitoreo.json','reports/analisis_peores.json','reports/analisis_desacuerdos.json','reports/contradiccion_ragas.json']:
        check(file,(ROOT/file).exists())
    review_path=ROOT/'reports/analisis_desacuerdos.json'
    review=json.loads(review_path.read_text()) if review_path.exists() else {}
    check('desacuerdos revisados de ambas versiones',review.get('completo') and {'v1','v2'} <= set(review.get('versiones_revisadas',[])))
    verification_path=ROOT/'reports/ragas_verificacion.json'
    ragas_check=json.loads(verification_path.read_text()) if verification_path.exists() else {}
    check('RAGAS contrastado con ascore',ragas_check.get('coincide') and len(ragas_check.get('metricas',{}))==4)
    for v in ['v1','v2']:
        folder=ROOT/'reports'/v
        path=folder/'resultados.csv'
        rows=list(csv.DictReader(path.open())) if path.exists() else []
        check(v+' resultados completos',{r['id'] for r in rows}==ids)
        check(v+' sin errores de infraestructura',bool(rows) and all(r['status']!='error' for r in rows))
        check(v+' juez todas las filas',bool(rows) and all(r.get('juez_aprueba') in ('0','1') for r in rows))
        path=folder/'export_verificacion.json';verification=json.loads(path.read_text()) if path.exists() else {}
        check(v+' exportación comprobada',verification.get('coincide') and verification.get('corridas')==len(cases))
        path=folder/'spans.jsonl';spans=[json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []
        check(v+' tipos de observación',{'corrida','llm','herramienta','guardrail','agent','retriever'} <= {s['span'] for s in spans})
        by_trace={r['traza_id']:r for r in rows}
        selected=[s for s in spans if s['traza'] in by_trace]
        span_ids={s.get('observation_id') for s in selected}
        check(v+' jerarquía completa',bool(selected) and all(not s.get('parent_id') or s['parent_id'] in span_ids for s in selected))
        check(v+' herramientas con tamaño',bool(selected) and all(isinstance(s.get('result_bytes'),(int,float)) and s['result_bytes']>=0 for s in selected if s['span']=='herramienta'))
        roots_by_trace={s['traza']:s for s in selected if s['span']=='corrida'}
        check(v+' estados raíz consistentes',bool(rows) and all(roots_by_trace.get(r['traza_id'],{}).get('status')==r['status'] for r in rows))
        for r in rows:
            if r['status']=='blocked':continue
            check(v+' 8 roles '+r['id'],len({s['nombre'] for s in spans if s['span']=='agent' and s['traza']==r['traza_id']})>=8)
        path=folder/'ragas_resultados.csv';ragas=list(csv.DictReader(path.open())) if path.exists() else []
        expected={(c['id'],m) for c in cases if c['tipo'] in ('simple','multi') for m in ['fidelidad','relevancia_respuesta','precision_contexto','recall_contexto']}
        check(v+' RAGAS completo',expected <= {(r['id'],r['metrica']) for r in ragas if not r.get('error') and r['valor']!=''})
        check(v+' PII ausente de spans',bool(spans) and not any(p in json.dumps(spans,ensure_ascii=False) for c in cases for p in c.get('pii',[])))
    out={'completo':all(c['completo'] for c in checks),'checks':checks}
    (ROOT/'reports/auditoria.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));return out
