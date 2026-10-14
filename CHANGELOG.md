# Cambios de Taller04

## v1 — línea base

Contrato `.run(pregunta)` y ocho roles LangGraph; GLM-5.3-Flash; RAG Qdrant
`taller04_kubernetes`; evaluación externa gpt-oss:120b; prompt SRE único registrado
como `taller04-incident-commander` en Langfuse. Guardrail de inyección con patrones
literales; redacción de PII y restricciones de ejecución activas desde el inicio.

## v2 — mejora del guardrail de inyección

Mismo modelo, juez, prompt y golden. Se normalizan tildes, se detectan intenciones de
extracción de reglas/credenciales y suplantación sin restricciones; se exceptúan
preguntas defensivas y negaciones explícitas. Se mide contra el mismo banco y golden.
La versión de implementación del guardrail se conserva como `prompt_version` en
spans por compatibilidad con el contrato del taller; la versión del prompt de
Langfuse se liga aparte a cada generación. No se afirma un cambio del prompt LLM.

El PDF `corpus/deliverable_taller04.pdf` conserva el contenido histórico del Taller03;
no se usa como verdad de referencia ni se reescribe la evidencia histórica.

La medición base encontró C13/C14: el modelo sí se abstuvo, pero añadió explicaciones
y violó el contrato de frase exacta. v2 añade canonicalización de salida cuando la
respuesta ya comienza con la abstención exacta; conserva el texto original en la
generación y registra la transformación en el span de guardrail. No inventa una
abstención desde una respuesta afirmativa. La ejecución preliminar v2 se archivó y
se repitió desde cero tras esta corrección para no mezclar implementaciones.

## Integridad de las mediciones

La verificación determinista compara la primera cantidad solicitada con el snapshot,
para evitar aprobar por la presencia incidental de otra cifra. Las exportaciones
cotejan todos los identificadores de observación y sus tokens con el testigo.
Los spans recuperados conservan su procedencia explícita; no se presentan como una
ingestión original sin interrupciones.

Los CSV se publican mediante reemplazo atómico. RAGAS conserva una entrada inmutable
y su hash, evitando lecturas parciales mientras el juez publica resultados. Se
conservan los veredictos originales, incluido el falso positivo del juez en C17.
Las cuatro métricas de C03 se contrastaron con `ragas.ascore` y coincidieron.

La CLI operativa `run` usa v2 por defecto, igual que `IncidentCommander()`. Los
comandos de evaluación mantienen v1 por defecto para preservar el orden del protocolo.
