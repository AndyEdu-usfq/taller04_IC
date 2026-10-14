"""RAGAS real en entorno separado. Reutiliza los prompts y fórmulas del profesor."""
from __future__ import annotations
import asyncio
import csv
import importlib.util
import json
import math
import hashlib
import io
import os
import sys
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")
from importlib.metadata import version as package_version
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def run(version):
    import subprocess
    python=os.getenv('RAGAS_PYTHON',str(ROOT/'.venv-ragas/bin/python'))
    subprocess.run([python,str(Path(__file__)),version],check=True)

async def evaluate(version):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.embeddings.base import embedding_factory
    spec=importlib.util.spec_from_file_location('juez_ragas',ROOT/'referencia/ragas-langfuse/juez_ragas.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    cli=AsyncOpenAI(base_url=os.getenv('JUEZ_BASE_URL','http://172.28.230.10:11434/v1'),api_key='ollama',timeout=180,max_retries=1)
    model=os.getenv('JUEZ_MODEL','gpt-oss:120b')
    sys.path.insert(0,str(ROOT/'src'))
    from taller04.models import OllamaJudge
    from taller04.evaluation import write_csv
    from ragas.llms.base import InstructorBaseRagasLLM
    native=OllamaJudge(timeout=600)
    class NativeAdapter(InstructorBaseRagasLLM):
        def generate(self,prompt,response_model):
            result=native.chat([{'role':'user','content':prompt}],schema=response_model.model_json_schema())
            return response_model.model_validate_json(result['contenido'])
        async def agenerate(self,prompt,response_model):
            return await asyncio.to_thread(self.generate,prompt,response_model)
    llm=NativeAdapter()
    print('RAGAS: mismo juez gpt-oss, think=low, contexto=16384; prompts oficiales sin cambios',flush=True)
    emb=embedding_factory('openai',model=os.getenv('EMBEDDING_MODEL','bge-m3:latest'),client=cli)
    judge=mod.JuezRAGAS(llm,emb)
    from taller04.observability import Recorder
    recorder=Recorder('taller04-ragas-'+version,version,output=ROOT/'reports'/version/'ragas_witness.jsonl')
    cases={c['id']:c for c in json.loads((ROOT/'golden_set.json').read_text())}
    folder=ROOT/'reports'/version;target=folder/'ragas_resultados.csv'
    rows=list(csv.DictReader(target.open())) if target.exists() else []
    for existing in rows:existing.setdefault('input_sha256','');existing.setdefault('cache_source','')
    done={(r['id'],r['metrica']) for r in rows if r.get('error','')==''}
    metric_cache=ROOT/'reports/ragas_metric_cache';metric_cache.mkdir(parents=True,exist_ok=True)
    def save_metric(path,data):
        temporary=path.with_suffix('.'+str(os.getpid())+'.tmp')
        temporary.write_text(json.dumps(data,ensure_ascii=False));temporary.replace(path)
    def key_for(metric,row,reference,contexts):
        inputs={'metric':metric,'question':row['pregunta'],'judge':model,'context_tokens':16384,'think':'low','temperature':0,'ragas':package_version('ragas'),'n_relevance':3}
        if metric in ('fidelidad','relevancia_respuesta'):inputs['answer']=row['answer']
        if metric!='relevancia_respuesta':inputs['contexts']=contexts
        if metric in ('precision_contexto','recall_contexto'):inputs['reference']=reference
        return hashlib.sha256(json.dumps(inputs,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    source_data=(folder/'resultados.csv').read_bytes()
    source_hash=hashlib.sha256(source_data).hexdigest()
    snapshot=folder/('ragas_input_'+source_hash[:16]+'.csv')
    if not snapshot.exists():snapshot.write_bytes(source_data)
    source_rows=list(csv.DictReader(io.StringIO(source_data.decode('utf-8'))))
    for r in source_rows:
        if r['tipo'] not in ('simple','multi') or r['status']=='error':continue
        contexts=[x['texto'] if isinstance(x,dict) else x for x in json.loads(r['contextos'])]
        if not contexts:continue
        reference=cases[r['id']]['respuesta_esperada']
        calls={'fidelidad':lambda:judge.fidelidad(r['pregunta'],r['answer'],contexts),'relevancia_respuesta':lambda:judge.relevancia_respuesta(r['pregunta'],r['answer']),'precision_contexto':lambda:judge.precision_contexto(r['pregunta'],reference,contexts),'recall_contexto':lambda:judge.recall_contexto(r['pregunta'],reference,contexts)}
        for metric,fn in calls.items():
            key=key_for(metric,r,reference,contexts);cache_file=metric_cache/(key+'.json')
            own=next((x for x in rows if x['id']==r['id'] and x['metrica']==metric and not x.get('error') and x.get('input_sha256')==key),None)
            if own:
                own['input_sha256']=key
                if not cache_file.exists():save_metric(cache_file,{'row':own,'source':str(target.relative_to(ROOT))})
                continue
            if cache_file.exists():
                data=json.loads(cache_file.read_text());saved=dict(data['row']);saved.update(id=r['id'],tipo=r['tipo'],input_sha256=key,cache_source=data['source'])
                rows=[x for x in rows if not(x['id']==r['id'] and x['metrica']==metric)]+[saved]
                write_csv(target,rows)
                print('RAGAS cache exacta',version,r['id'],metric,flush=True)
                continue
            try:
                print('RAGAS inicia',r['id'],metric,flush=True)
                with recorder.run('RAGAS '+r['id']+' '+metric):
                    value,detail=await fn()
                error=''
            except Exception as exc:
                value=float('nan');detail='';error=str(exc)
            rows=[x for x in rows if not(x['id']==r['id'] and x['metrica']==metric)]
            rows.append({'id':r['id'],'tipo':r['tipo'],'metrica':metric,'valor':'' if math.isnan(value) else value,'comentario':detail,'error':error,'juez':model,'ragas':package_version('ragas'),'input_sha256':key,'cache_source':''})
            if not error and not math.isnan(value):save_metric(cache_file,{'row':rows[-1],'source':str(target.relative_to(ROOT))})
            write_csv(target,rows)
            print('RAGAS',version,r['id'],metric,value,error[:150],flush=True)

if __name__=='__main__': asyncio.run(evaluate(sys.argv[1]))
