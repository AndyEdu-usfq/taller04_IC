"""API Kubernetes simulada. Nunca invoca un shell ni un cluster real."""
from __future__ import annotations
import copy
import hashlib
import json
import shlex
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

class KubernetesSimulator:
    def __init__(self, snapshot=None):
        self.state = copy.deepcopy(snapshot or json.loads((ROOT/'data/kubernetes.json').read_text()))
        self.mutations=[]
    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.state, sort_keys=True).encode()).hexdigest()
    def kubectl(self, command):
        args=shlex.split(command)
        if not args or args.pop(0) != 'kubectl' or any(c in command for c in ';|&><$`\n'):
            raise ValueError('Comando no permitido')
        namespace=None
        if '-n' in args:
            i=args.index('-n'); namespace=args[i+1]; del args[i:i+2]
        if '--namespace' in args:
            i=args.index('--namespace'); namespace=args[i+1]; del args[i:i+2]
        if len(args)<2 or args[0]!='get': raise ValueError('Solo get en el lector')
        kind=args[1]
        aliases={'deploy':'deployments','deployment':'deployments','pod':'pods','event':'events','endpoint':'endpoints','alert':'alerts'}
        kind=aliases.get(kind,kind)
        if kind not in self.state: raise ValueError('Recurso no disponible')
        rows=copy.deepcopy(self.state[kind])
        if namespace: rows=[r for r in rows if r.get('namespace')==namespace]
        tail=args[2:]
        if tail and not tail[0].startswith('-'):
            name=tail.pop(0); rows=[r for r in rows if r.get('name',r.get('id'))==name]
        if tail not in ([],['-o','json'],['-A'],['-A','-o','json']): raise ValueError('Opciones no permitidas')
        return {'apiVersion':'simulator.taller04/v1','kind':kind,'items':rows,'simulado':True}
    def restart(self, namespace, deployment, approved=False):
        from .guardrails import permitir_reinicio
        policy=permitir_reinicio(namespace,deployment,approved)
        if policy['decision']=='bloquear': return {'status':'blocked','policy':policy,'simulado':True}
        target=next((x for x in self.state['deployments'] if x['namespace']==namespace and x['name']==deployment),None)
        if target is None: return {'status':'not_found','simulado':True}
        target['restarts']=target.get('restarts',0)+1
        self.mutations.append({'namespace':namespace,'deployment':deployment})
        return {'status':'restarted','simulado':True,'deployment':copy.deepcopy(target)}
