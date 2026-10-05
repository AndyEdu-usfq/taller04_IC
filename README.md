## Taller 03: MCP de telemetría

Servidor MCP local que emula una herramienta de observabilidad para alertas de
Kubernetes. Expone alertas P1, P2 y P3 deterministas, sin conectarse todavía a
Prometheus, New Relic, Datadog ni a un clúster real.

### Ejecutar

```bash
uv sync
uv run taller03
```

El servidor usa `stdio`, que es el transporte esperado por clientes MCP locales.
Para probar la lógica sin iniciar el transporte:

```bash
uv run python -c "from taller03.telemetry_mcp import list_alerts, summarize_alerts; print(list_alerts(severity='P1')); print(summarize_alerts())"
```

### Herramientas

- `list_alerts`: filtra por `severity`, `status` y `namespace`. Por defecto devuelve alertas activas.
- `get_alert`: obtiene el detalle de una alerta por `alert_id`.
- `summarize_alerts`: cuenta alertas por severidad.

El siguiente paso será conectar estas herramientas al agente y, después, reemplazar
la colección en memoria por consultas a la fuente de telemetría elegida.

### Cliente H200

El cliente reutilizable está en `src/taller03/h200.py`. Descubre los modelos
servidos, por lo que no requiere escribir un id de modelo ni una API key:

```python
from taller03.h200 import H200

h200 = H200()
respuesta = h200.chat([
	{"role": "user", "content": "¿Qué es un Pod en Kubernetes?"},
])
vectores = h200.embeddings(["Kubernetes Pod", "Kubernetes Service"])
```

Variables opcionales: `H200_HOST`, `H200_LLM_PORT`, `H200_EMB_PORT`,
`H200_EMBEDDING_PREFIX`. Por defecto usa `172.28.230.10`, los puertos `12555`
y `11434`, y el modelo de embeddings cuyo id comienza por `bge-m3`.

### RAG con la H200

`rag_taller03.py` indexa los PDFs del folder `corpus` en Qdrant local, recupera
por similitud coseno y genera exclusivamente con la H200. No usa OpenAI,
Anthropic ni API keys:

```bash
uv sync
docker run -p 6333:6333 qdrant/qdrant
uv run python -m taller03.rag_taller03 "¿Qué componentes tiene el control plane de Kubernetes?"
```

Por defecto usa `http://localhost:6333` y la colección `taller03_kubernetes`.
Se pueden cambiar con `QDRANT_URL`, `QDRANT_COLLECTION` y `QDRANT_API_KEY`.
Cada ejecución de `indexar()` reemplaza la colección para que el corpus y sus
embeddings queden sincronizados.

### Incident Commander con LangGraph

El módulo `src/taller03/incident_commander.py` conecta el MCP de telemetría, el
RAG y la revisión humana:

```python
from langgraph.types import Command
from taller03.incident_commander import IncidentMemory, build_graph
from taller03.rag_taller03 import RagTaller03

rag = RagTaller03()
rag.indexar()
graph = build_graph(rag=rag, memory=IncidentMemory())
config = {"configurable": {"thread_id": "incident-demo"}}

paused = graph.invoke({}, config)                 # llega a la aprobación humana
finished = graph.invoke(Command(resume={"approved": False}), config)
```

El grafo detecta la alerta activa de mayor prioridad, clasifica P1/P2/P3,
propone código de remediación con el RAG, se pausa antes de cualquier ejecución,
genera el Post-Incident Review y guarda el incidente en
`output_data/incident_memory.sqlite3`. Cada nodo agrega tokens, latencia, timestamp y
detalles a `_traza`. No existe un nodo ejecutor: una propuesta aprobada queda
marcada como `approved_not_executed` hasta que se añada un ejecutor explícito.

El flujo también incluye `self_reflect`, `external_judge` y `policy_gate`. El
modo autónomo se activa únicamente con `autonomous=True` y un `executor` inyectado;
la política solo permite acciones estructuradas de rollout restart y bloquea
shell, pipes, borrados y comandos no incluidos en la allowlist. Sin executor, el
resultado siempre es `not_executed`.
