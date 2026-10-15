# Ajuste local aplicado a ClickHouse

Se observaron errores `MEMORY_LIMIT_EXCEEDED` durante inserciones y fusiones,
con Docker limitado a 3.823 GiB. Se añadieron los dos XML de esta carpeta a
`config.d/taller04-low-memory.xml` y `users.d/taller04-low-memory.xml` del contenedor
`langfuse-mmia-clickhouse-1`, y se reinició solo ese contenedor. No se borraron datos
ni volúmenes. Reduce memoria de servidor a 1.8 GB, concurrencia a dos y fusiones
a 64 MiB. No pretende ser configuración de producción.

Para reproducir, montar estos XML como solo lectura en los mismos destinos en
Docker Compose. La modificación aplicada con docker cp dura mientras exista el
contenedor; una recreación requiere esos mounts. Para revertir, retirar ambos
archivos adicionales o mounts y reiniciar ClickHouse.

Fuente técnica: https://github.com/ClickHouse/ClickHouse/blob/master/src/Storages/MergeTree/MergeTreeSettings.cpp

Los spans que el SDK perdió antes de esta corrección se recuperan con `taller04
recover --version v1`: misma medición local, IDs y respuestas, procedencia marcada
como `recovered_from_witness`; el inicio se deriva del fin UTC menos la duración
monotónica. No se vuelven a generar respuestas ni se alteran etiquetas humanas.
La entrega sigue siendo `spans.jsonl` consultado/exportado del servidor y cotejado
contra los tokens originales. La implementación final añade una cola OTLP durable
que conserva los mensajes originales hasta que el servidor los acepte.
