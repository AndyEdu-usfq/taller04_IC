# Taller04 — Incident Commander Kubernetes + LLMOps (opción C)

Kubernetes y alertas son **simulados**; las inferencias GLM-5.3-Flash y gpt-oss:120b,
embeddings H200, Qdrant y observaciones Langfuse son reales. Requiere VPN GlobalProtect.
Ocho roles LangGraph: telemetría, triage, investigación RAG, remediación, revisión,
ejecución simulada, PIR y memoria. Nunca invoca shell o kubectl real.

## Preparar

### Prerrequisitos

Ejecutar desde la raíz de `taller04/`, con `uv` instalado. Se usa Python 3.12;
`uv sync --python 3.12` prepara el entorno y puede necesitar Internet para descargar
Python y dependencias. El directorio `.venv` no se copia entre equipos.

Antes de ejecutar `doctor`:

- Conectar GlobalProtect a la red de la universidad. Deben estar disponibles el
  agente en `172.28.230.10:12555` y Ollama en `172.28.230.10:11434`, con los modelos
  declarados en `.env`.
- Abrir Docker Desktop y levantar Langfuse. En esta estructura de carpetas se puede
  usar `bash ../taller-04-llmops/langfuse/levantar_langfuse.sh`. La configuración y
  los volúmenes del servicio están fuera de este repositorio. Ver `infra/README.md`
  para el ajuste de memoria usado durante las mediciones.
- Tener Qdrant disponible en `http://localhost:6333` (o en `QDRANT_URL`). Este
  repositorio no incluye un Compose que lo levante: hay que iniciar el servicio
  Qdrant del entorno y conservar su almacenamiento para reutilizar el índice.
- Configurar `.env` con las URLs y las claves API del proyecto Langfuse. Las claves
  `LANGFUSE_PUBLIC_KEY` y `LANGFUSE_SECRET_KEY` se obtienen en la configuración del
  proyecto; son distintas del correo y contraseña para entrar a la interfaz.

`doctor` comprueba servicios reales; no los instala ni los inicia. Comprueba agente,
juez, autenticación Langfuse, colecciones Qdrant y lectura del golden. Se detiene
en el primer error; no comprueba embeddings ni que el índice esté listo.

```bash
uv sync --python 3.12
cp .env.example .env
# Completar LANGFUSE_* con las claves del proyecto local; nunca publicarlas.
uv run taller04 doctor
uv run taller04 setup
uv run taller04 index
```

**Si `.env` ya existe, conservarlo:** no repetir `cp .env.example .env`, porque
sobrescribe sus claves. `setup` registra el prompt en Langfuse e `index` reconstruye
la colección: son preparación inicial, no pasos necesarios cada vez que se opera.

Si aparece `not a valid Python environment (no Python executable was found)`,
el entorno está incompleto. Desde `taller04/`, renombrarlo con un nombre libre y
recrearlo:

```bash
mv .venv .venv.incompleto
uv sync --python 3.12
uv run taller04 doctor
```

Si el error menciona `Failed to initialize cache` o permisos sobre `~/.cache/uv`,
se puede seleccionar una caché escribible para ese comando:
`UV_CACHE_DIR=/tmp/taller04-uv-cache uv sync --python 3.12`.
Si aparece conexión rechazada en localhost, revisar Langfuse/Qdrant; si hay timeout
hacia `172.28.230.10`, revisar VPN y disponibilidad de la H200. Si el modelo no está
disponible, comprobar los nombres declarados en `.env` con el administrador del
servidor antes de cambiar la configuración de las mediciones.

`index` reconstruye solo la colección `taller04_kubernetes` a partir de
`data/knowledge`. La colección anterior no se borra. `data/kubernetes.json` contiene
la verdad del simulador. `corpus/` y el grafo anterior se preservan como antecedentes.
Las consultas `kubectl_verificacion` del golden se ejecutan sobre ese snapshot,
independientemente de la respuesta LLM.

## Operar

```bash
uv run taller04 run --version v2 --question '¿Cuántas alertas P1 firing hay?'
uv run taller04-mcp  # servidor MCP: list_alerts, get_alert, summarize_alerts, kubectl_simulado
```

`.run()` devuelve answer, trace (agente/tool), status, model, usage medido,
contextos, traza_id, prompt_version, latencia_ms y ambiente_intacto. La operación
normal no reinicia recursos: el simulador exige aprobación externa y allowlist.
Una integración puede llamar `KubernetesSimulator.restart(..., approved=True)`;
solo admite payments/checkout-api y no actúa sobre Kubernetes real.

## Medir → cambiar → volver a medir

```bash
uv run taller04 part0
uv run taller04 guardrails
uv run taller04 preflight                 # 10 controles balanceados, antes de usar el juez
uv run taller04 evaluate --version v1
# Revisar reports/v1/revision_ciega.json, SIN ejecutar judge todavía.
# Crear etiquetas.csv: id,etiqueta; >=10 filas, incluida C11 y C12; aprueba/falla.
uv run taller04 judge --version v1
uv run taller04 evaluate --version v2
uv run taller04 judge --version v2
uv run taller04 export --version v1
uv run taller04 export --version v2
```

La evaluación guarda resultados por caso y permite continuar una ejecución incompleta.
No reutilizar reports/v1 o reports/v2 después de cambiar modelo, prompt, datos o golden:
archivar esos directorios y repetir ambas versiones. La versión del guardrail (v1/v2)
es la mejora experimental; el prompt LLM se mantiene constante (CHANGELOG.md).
Exportar después de que Langfuse haya ingerido los spans; el exportador comprueba
corridas, tokens contra el testigo y ausencia de PII del golden. `witness*.jsonl` es
solo verificación local, **no sustituye** `spans.jsonl` exportado del servidor.

## RAGAS e informe

```bash
uv venv .venv-ragas --python 3.12
uv pip install --python .venv-ragas/bin/python -r requirements-ragas.lock.txt
uv run taller04 ragas --version v1
uv run taller04 ragas --version v2
uv run taller04 report
uv run pytest -q
```

RAGAS 0.4.3 va en otro entorno por incompatibilidad entre LangChain 0.3 y el
LangGraph actual. Se usan las cuatro métricas reales del profesor y gpt-oss:120b:
fidelidad, relevancia, precisión y recall de contexto. El cálculo guarda resultados
incrementales y errores explícitos; un error no se convierte en cero.

Los artefactos quedan en `reports/`: CSV base/mejorada, spans, verificaciones de
exportación, RAGAS, guardrails propios/ejemplo, calibraciones, comparación, peores
casos, alertas con umbrales medidos, grafo Mermaid e informe MD/PDF. Las tarifas
hipotéticas son las del anexo docente (fila/fecha declaradas), no precios actuales.

## Privacidad y límites

Redacción recursiva de correos, cédula y teléfonos ecuatorianos en entrada, salida,
trazas y memoria. No hay NER: los nombres de personas pueden escapar. Los patrones
no prueban seguridad ante ataques desconocidos. Veinte casos dan resolución de 5 %
y no sostienen mejoras estadísticas pequeñas. Las etiquetas humanas deben ser
humanas: el programa no las inventa y bloquea el juez base mientras falten.

`referencia/` contiene los laboratorios del profesor sin cambiar sus errores
intencionales; la Parte 0 se ejecuta sobre ellos. La implementación previa del
Taller03 sigue en `incident_commander.py`, `h200.py` y `rag_taller04.py`.

## Juez compartido y reanudación

El juez usa API nativa Ollama, think=low y contexto de 16384 por solicitud,
porque el contexto predeterminado de 4096 truncaba evidencia RAGAS. No se modifica
la configuración del servidor compartido. Se serializan nuestras solicitudes con
un lock local para no provocar timeouts en la cola; cada veredicto y métrica
terminados se conservan para continuar sin repetirlos. La caché lleva SHA-256 de
las entradas completas y configuración; solo reutiliza juicios reales idénticos.
Las lecturas de caché tienen span tool y cero tokens nuevos. Los CSV RAGAS incluyen
input_sha256 y cache_source. No se estima variabilidad de réplicas con esa caché.

Tras una indisponibilidad de Langfuse: `uv run taller04 drain`, exportar y cotejar.
`recover` es una migración explícita para las mediciones anteriores a la cola OTLP;
conserva IDs/tokens/respuestas, deriva inicio de fin menos duración y marca
recovered_from_witness. Ver infra/README.md.

El modo de aprobación del simulador se activa explícitamente con
`uv run taller04 run --version v2 --approve-restart --question 'Reinicia checkout-api en payments'`.
Ese flag concede aprobación solo para ese objetivo; no ejecuta nada en Kubernetes real.
