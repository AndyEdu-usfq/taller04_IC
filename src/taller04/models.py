"""Clientes H200 con selección explícita del modelo y uso real del proveedor."""
from __future__ import annotations
import json
import os
import urllib.request
from .observability import ACTIVE

class ModelClient:
    def __init__(self, role='agent', timeout=180):
        self.role=role; self.timeout=timeout
        self.url=os.getenv('AGENT_BASE_URL' if role=='agent' else 'JUEZ_BASE_URL',f'http://172.28.230.10:{12555 if role=="agent" else 11434}/v1').rstrip('/')
        self.model=os.getenv('AGENT_MODEL' if role=='agent' else 'JUEZ_MODEL','zai-org/GLM-5.3-Flash' if role=='agent' else 'gpt-oss:120b')
    def request(self,path,body=None):
        req=urllib.request.Request(self.url+'/'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer local'})
        with urllib.request.urlopen(req,timeout=self.timeout) as r: return json.load(r)
    def validate(self):
        ids=[x['id'] for x in self.request('models')['data']]
        if self.model not in ids: raise ValueError(f'Modelo {self.model} no disponible. Disponibles: {ids}')
        return {'role':self.role,'url':self.url,'model':self.model,'available':True}
    def chat(self,messages,json_mode=False,max_tokens=6000,prompt=None):
        rec=ACTIVE.get()
        body={'model':self.model,'messages':messages,'temperature':0,'max_tokens':max_tokens}
        if self.role=='agent': body['chat_template_kwargs']={'enable_thinking':False}
        if json_mode: body['response_format']={'type':'json_object'}
        def perform(row=None):
            r=self.request('chat/completions',body)
            if r.get('model') and r['model'] != self.model: raise RuntimeError('El servidor respondió con un modelo distinto al solicitado')
            msg=r['choices'][0]['message']; usage=r.get('usage')
            if not usage or 'prompt_tokens' not in usage or 'completion_tokens' not in usage:
                raise RuntimeError('El proveedor no devolvió tokens medidos')
            if row is not None: row.update(modelo=self.model,tokens_entrada=usage['prompt_tokens'],tokens_salida=usage['completion_tokens'],output=msg,prompt=prompt)
            if r['choices'][0].get('finish_reason')=='length': raise RuntimeError('Respuesta truncada por presupuesto de tokens')
            return {'contenido':msg.get('content') or '', 'uso':usage,'modelo':self.model}
        if rec:
            with rec.span('llm',self.role,messages) as row: return perform(row)
        return perform()
    def json(self,system,payload):
        result=self.chat([{'role':'system','content':system},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],json_mode=True)
        parsed=json.loads(result['contenido'])
        if not isinstance(parsed,dict): raise ValueError('Se esperaba objeto JSON')
        return parsed

class Embeddings:
    def __init__(self):
        self.url=os.getenv('EMBEDDING_BASE_URL','http://172.28.230.10:11434/v1').rstrip('/')
        self.model=os.getenv('EMBEDDING_MODEL','bge-m3:latest')
    def embeddings(self,texts):
        rec=ACTIVE.get()
        def perform(row=None):
            req=urllib.request.Request(self.url+'/embeddings',data=json.dumps({'model':self.model,'input':texts}).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=180) as response: result=json.load(response)
            if row is not None:
                row['output']={'count':len(result['data']),'dimension':len(result['data'][0]['embedding'])}
                row['modelo']=self.model
                row['tokens_entrada']=result.get('usage',{}).get('prompt_tokens',0); row['tokens_salida']=0
                row['usage_available']='usage' in result
            return [x['embedding'] for x in sorted(result['data'],key=lambda x:x['index'])]
        if rec:
            with rec.span('llm','embeddings',texts) as row: return perform(row)
        return perform()

class OllamaJudge(ModelClient):
    """Contexto explícito, cola local entre evaluadores y caché de solicitudes idénticas."""
    def __init__(self, timeout=600):
        super().__init__('judge',timeout)
    def chat(self,messages,json_mode=False,max_tokens=6000,prompt=None,schema=None):
        import fcntl, hashlib
        from contextlib import nullcontext
        from datetime import datetime, timezone
        from pathlib import Path
        from .guardrails import mask
        rec=ACTIVE.get()
        body={'model':self.model,'messages':messages,'stream':False,'think':'low','options':{'temperature':0,'num_ctx':int(os.getenv('JUEZ_CONTEXT_TOKENS','16384')),'num_predict':max_tokens}}
        if schema: body['format']=schema
        elif json_mode:body['format']='json'
        root=Path(__file__).resolve().parents[2]/'reports'
        cache=root/'judge_cache';cache.mkdir(parents=True,exist_ok=True)
        key=hashlib.sha256(json.dumps({'url':self.url,'body':body},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        target=cache/(key+'.json')
        def cached():
            data=json.loads(target.read_text())
            return {**data['result'],'uso':{'prompt_tokens':0,'completion_tokens':0},'cache_hit':True,'cache_key':key,'source_trace':data.get('source_trace')}
        if target.exists():
            return rec.call('herramienta','judge.cache',cached) if rec else cached()
        with (root/'judge.lock').open('a') as lock:
            if rec:
                with rec.span('herramienta','judge.scheduler') as queue:
                    fcntl.flock(lock,fcntl.LOCK_EX);queue['output']={'acquired':True}
            else:fcntl.flock(lock,fcntl.LOCK_EX)
            try:
                if target.exists():
                    return rec.call('herramienta','judge.cache',cached) if rec else cached()
                with (rec.span('llm','judge',messages) if rec else nullcontext(None)) as row:
                    req=urllib.request.Request(self.url.removesuffix('/v1')+'/api/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(req,timeout=self.timeout) as response:r=json.load(response)
                    usage={'prompt_tokens':r['prompt_eval_count'],'completion_tokens':r['eval_count']}
                    if row is not None:row.update(modelo=self.model,tokens_entrada=usage['prompt_tokens'],tokens_salida=usage['completion_tokens'],output=r['message'],reasoning_effort='low',context_tokens=body['options']['num_ctx'])
                    if r.get('done_reason')=='length':raise RuntimeError('Juez truncado por presupuesto de tokens')
                    if json_mode or schema:json.loads(r['message'].get('content',''))
                    result={'contenido':r['message'].get('content',''),'uso':usage,'modelo':r.get('model',self.model)}
                    data={'result':result,'input_sha256':key,'source_trace':row.get('traza') if row else None,'created_utc':datetime.now(timezone.utc).isoformat(),'reasoning_effort':'low','context_tokens':body['options']['num_ctx']}
                    tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(mask(data),ensure_ascii=False));tmp.replace(target)
                    return result
            finally:fcntl.flock(lock,fcntl.LOCK_UN)
