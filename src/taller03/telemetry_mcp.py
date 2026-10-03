"""Read-only MCP server that emulates Kubernetes telemetry alerts."""

from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP


Severity = Literal["P1", "P2", "P3"]
AlertStatus = Literal["firing", "resolved"]

ALERTS: list[dict[str, object]] = [
    {
        "id": "k8s-prod-api-001",
        "severity": "P1",
        "status": "firing",
        "cluster": "prod-us-east-1",
        "namespace": "payments",
        "service": "checkout-api",
        "summary": "Checkout API error rate above 20%",
        "description": "HTTP 5xx responses have exceeded the critical threshold for 10 minutes.",
        "started_at": "2026-10-03T09:42:00Z",
        "runbook_url": "https://runbooks.example.com/payments/checkout-api-errors",
        "labels": {"team": "payments", "tier": "critical"},
    },
    {
        "id": "k8s-prod-db-002",
        "severity": "P2",
        "status": "firing",
        "cluster": "prod-us-east-1",
        "namespace": "orders",
        "service": "orders-worker",
        "summary": "Orders queue lag is growing",
        "description": "Consumer lag is above 5,000 messages and increasing steadily.",
        "started_at": "2026-10-03T09:15:00Z",
        "runbook_url": "https://runbooks.example.com/orders/queue-lag",
        "labels": {"team": "orders", "tier": "important"},
    },
    {
        "id": "k8s-staging-web-003",
        "severity": "P3",
        "status": "firing",
        "cluster": "staging-eu-west-1",
        "namespace": "web",
        "service": "frontend",
        "summary": "Frontend pods restarting occasionally",
        "description": "The deployment has recorded intermittent CrashLoopBackOff events.",
        "started_at": "2026-10-03T08:30:00Z",
        "runbook_url": "https://runbooks.example.com/web/frontend-restarts",
        "labels": {"team": "web", "tier": "standard"},
    },
    {
        "id": "k8s-prod-cache-004",
        "severity": "P2",
        "status": "resolved",
        "cluster": "prod-us-east-1",
        "namespace": "catalog",
        "service": "redis",
        "summary": "Redis memory pressure",
        "description": "Redis memory usage exceeded 85% before returning to normal levels.",
        "started_at": "2026-10-03T07:05:00Z",
        "runbook_url": "https://runbooks.example.com/catalog/redis-memory",
        "labels": {"team": "catalog", "tier": "important"},
    },
]

mcp = FastMCP("kubernetes-telemetry")


def _matches(
    alert: dict[str, object],
    severity: Severity | None = None,
    status: AlertStatus | None = None,
    namespace: str | None = None,
) -> bool:
    return (
        (severity is None or alert["severity"] == severity)
        and (status is None or alert["status"] == status)
        and (namespace is None or alert["namespace"] == namespace)
    )


@mcp.tool()
def list_alerts(
    severity: Severity | None = None,
    status: AlertStatus | None = "firing",
    namespace: str | None = None,
) -> list[dict[str, object]]:
    """List Kubernetes alerts, optionally filtered by severity, status, or namespace."""
    return [
        alert.copy()
        for alert in ALERTS
        if _matches(alert, severity=severity, status=status, namespace=namespace)
    ]


@mcp.tool()
def get_alert(alert_id: str) -> dict[str, object]:
    """Return one Kubernetes alert by id, or a not-found result."""
    for alert in ALERTS:
        if alert["id"] == alert_id:
            return alert.copy()
    return {"error": "alert_not_found", "alert_id": alert_id}


@mcp.tool()
def summarize_alerts(status: AlertStatus | None = "firing") -> dict[str, object]:
    """Return alert counts grouped by P1, P2, and P3."""
    selected = [alert for alert in ALERTS if status is None or alert["status"] == status]
    by_severity = {severity: sum(alert["severity"] == severity for alert in selected) for severity in ("P1", "P2", "P3")}
    return {"status": status or "all", "total": len(selected), "by_severity": by_severity}


if __name__ == "__main__":
    mcp.run(transport="stdio")