"""Cola OTLP durable. Reenvía los mismos spans/IDs; luego se exportan de Langfuse."""
from __future__ import annotations
import base64
import hashlib
import os
from pathlib import Path
import urllib.request
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans

ROOT=Path(__file__).resolve().parents[2]

def send(path):
    auth=base64.b64encode((os.environ['LANGFUSE_PUBLIC_KEY']+':'+os.environ['LANGFUSE_SECRET_KEY']).encode()).decode()
    endpoint=os.getenv('LANGFUSE_BASE_URL',os.getenv('LANGFUSE_HOST','http://localhost:3000')).rstrip('/')+'/api/public/otel/v1/traces'
    request=urllib.request.Request(endpoint,data=path.read_bytes(),headers={'Content-Type':'application/x-protobuf','Authorization':'Basic '+auth,'x-langfuse-sdk-name':'python','x-langfuse-sdk-version':'4.17.0'})
    with urllib.request.urlopen(request,timeout=20) as response:
        if response.status not in (200,202,204): raise RuntimeError('Ingestión OTLP no aceptada')
    path.unlink()

class DurableExporter(SpanExporter):
    def __init__(self,folder=None):
        self.folder=Path(folder or ROOT/'reports/otlp_pending');self.folder.mkdir(parents=True,exist_ok=True)
    def export(self,spans):
        data=encode_spans(spans).SerializeToString()
        path=self.folder/(hashlib.sha256(data).hexdigest()+'.otlp')
        temp=path.with_suffix('.tmp');temp.write_bytes(data);temp.replace(path)
        try: send(path)
        except Exception:
            # Already durably stored; the explicit drain command retries.
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS
    def shutdown(self): pass

def drain():
    folder=ROOT/'reports/otlp_pending';sent=0
    for path in sorted(folder.glob('*.otlp')):
        send(path);sent+=1
    return {'reenviados':sent,'pendientes':len(list(folder.glob('*.otlp')))}
