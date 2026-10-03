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
