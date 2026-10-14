"""Contrasta las fórmulas docentes con ragas.ascore usando los juicios ya medidos."""
from __future__ import annotations
import asyncio,csv,json,os,sys,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))

async def verify(version='v1',case_id='C03'):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    os.environ.setdefault('RAGAS_DO_NOT_TRACK','true')
    from openai import AsyncOpenAI
    from ragas.llms.base import InstructorBaseRagasLLM
    from ragas.embeddings.base import embedding_factory
    from taller04.models import OllamaJudge
    from taller04.observability import Recorder
    spec=importlib.util.spec_from_file_location('juez_ragas',ROOT/'referencia/ragas-langfuse/juez_ragas.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    client=OllamaJudge()
    class Adapter(InstructorBaseRagasLLM):
        def generate(self,prompt,response_model):
            r=client.chat([{'role':'user','content':prompt}],schema=response_model.model_json_schema())
            return response_model.model_validate_json(r['contenido'])
        async def agenerate(self,prompt,response_model):return await asyncio.to_thread(self.generate,prompt,response_model)
    emb=embedding_factory('openai',model=os.getenv('EMBEDDING_MODEL','bge-m3:latest'),client=AsyncOpenAI(base_url=os.getenv('JUEZ_BASE_URL','http://172.28.230.10:11434/v1'),api_key='ollama',timeout=180))
    judge=mod.JuezRAGAS(Adapter(),emb)
    row=next(r for r in csv.DictReader((ROOT/f'reports/{version}/resultados.csv').open()) if r['id']==case_id)
    expected={r['metrica']:float(r['valor']) for r in csv.DictReader((ROOT/f'reports/{version}/ragas_resultados.csv').open()) if r['id']==case_id and r['valor']!='' and not r['error']}
    if len(expected)!=4:raise RuntimeError('Esperar las cuatro métricas del caso antes de verificar')
    case=next(c for c in json.loads((ROOT/'golden_set.json').read_text()) if c['id']==case_id)
    ctx=[c['texto'] for c in json.loads(row['contextos'])]
    calls={'fidelidad':lambda:judge.f.ascore(user_input=row['pregunta'],response=row['answer'],retrieved_contexts=ctx),'relevancia_respuesta':lambda:judge.ar.ascore(user_input=row['pregunta'],response=row['answer']),'precision_contexto':lambda:judge.cp.ascore(user_input=row['pregunta'],reference=case['respuesta_esperada'],retrieved_contexts=ctx),'recall_contexto':lambda:judge.cr.ascore(user_input=row['pregunta'],reference=case['respuesta_esperada'],retrieved_contexts=ctx)}
    rec=Recorder('taller04-verificar-ragas',version,output=ROOT/'reports/ragas_verify_witness.jsonl');results={}
    for name,fn in calls.items():
        with rec.run('ascore '+case_id+' '+name):value=float((await fn()).value)
        results[name]={'docente':expected[name],'ragas_ascore':value,'coincide':abs(value-expected[name])<1e-6}
        print(name,results[name],flush=True)
    out={'id':case_id,'version':version,'coincide':all(r['coincide'] for r in results.values()),'metricas':results}
    (ROOT/'reports/ragas_verificacion.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    if not out['coincide']:raise RuntimeError('Las fórmulas no coinciden con ragas.ascore')

if __name__=='__main__':asyncio.run(verify(*sys.argv[1:]))
