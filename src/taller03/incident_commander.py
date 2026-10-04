"""Incident Commander con LangGraph, RAG, aprobacion humana y memoria SQLite."""

from __future__ import annotations

import json
import operator
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from taller03.rag_taller03 import RagTaller03


PROJECT_DIR = Path(__file__).resolve().parents[2]
MEMORY_PATH = PROJECT_DIR / "corpus" / "incident_memory.sqlite3"
Priority = Literal["P1", "P2", "P3"]


class IncidentState(TypedDict, total=False):
    incident_id: str
    alerts: list[dict[str, Any]]
    selected_alert: dict[str, Any]
    priority: Priority
    triage: dict[str, Any]
    remediation: dict[str, Any]
    approval: dict[str, Any]
    review: dict[str, Any]
    preventive_actions: list[str]
    historical_incidents: list[dict[str, Any]]
    _traza: Annotated[list[dict[str, Any]], operator.add]


class RAGProtocol(Protocol):
    def responder(self, pregunta: str, top_k: int = 5, max_tokens: int = 512) -> dict[str, Any]: ...


class IncidentMemory:
    """Memoria durable y pequeña para revisiones y acciones preventivas."""

    def __init__(self, path: Path = MEMORY_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS incidents (
                    incident_id TEXT PRIMARY KEY,
                    priority TEXT NOT NULL,
                    alert_id TEXT NOT NULL,
                    namespace TEXT,
                    service TEXT,
                    review_json TEXT NOT NULL,
                    preventive_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )

    def find_similar(self, alert: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """SELECT incident_id, priority, alert_id, namespace, service,
                          review_json, preventive_json, created_at
                     FROM incidents
                    WHERE namespace = ? OR service = ?
                    ORDER BY created_at DESC LIMIT ?""",
                (alert.get("namespace"), alert.get("service"), limit),
            ).fetchall()
        return [
            {
                "incident_id": row[0],
                "priority": row[1],
                "alert_id": row[2],
                "namespace": row[3],
                "service": row[4],
                "review": json.loads(row[5]),
                "preventive_actions": json.loads(row[6]),
                "created_at": row[7],
            }
            for row in rows
        ]

    def save(self, state: IncidentState) -> None:
        alert = state["selected_alert"]
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """INSERT OR REPLACE INTO incidents
                    (incident_id, priority, alert_id, namespace, service,
                     review_json, preventive_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    state["incident_id"],
                    state["priority"],
                    alert.get("id", ""),
                    alert.get("namespace"),
                    alert.get("service"),
                    json.dumps(state.get("review", {}), ensure_ascii=False),
                    json.dumps(state.get("preventive_actions", []), ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )


class TelemetryClient(Protocol):
    def firing_alerts(self) -> list[dict[str, Any]]: ...


class LocalTelemetryClient:
    """Adaptador local del MCP simulado; luego puede reemplazarse por un cliente MCP real."""

    def firing_alerts(self) -> list[dict[str, Any]]:
        from taller03.telemetry_mcp import list_alerts

        return list_alerts(status="firing")


def _trace(node: str, started: float, result: dict[str, Any] | None = None,
           **details: Any) -> dict[str, Any]:
    usage = (result or {}).get("uso", {})
    return {
        "nodo": node,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latencia_s": round(time.perf_counter() - started, 3),
        "tokens_entrada": usage.get("prompt_tokens", 0),
        "tokens_salida": usage.get("completion_tokens", 0),
        **details,
    }


def _priority(alert: dict[str, Any]) -> Priority:
    value = alert.get("severity")
    return value if value in ("P1", "P2", "P3") else "P3"


def detect_telemetry(state: IncidentState, telemetry: TelemetryClient) -> dict[str, Any]:
    started = time.perf_counter()
    alerts = telemetry.firing_alerts()
    if not alerts:
        return {"alerts": [], "_traza": [_trace("detect_telemetry", started, alert_count=0)]}
    selected = sorted(alerts, key=lambda alert: (int(_priority(alert)[1]), alert.get("id", "")))[0]
    incident_id = f"incident-{selected.get('id', uuid.uuid4().hex[:8])}"
    return {
        "incident_id": incident_id,
        "alerts": alerts,
        "selected_alert": selected,
        "priority": _priority(selected),
        "_traza": [_trace("detect_telemetry", started, alert_count=len(alerts), alert_id=selected.get("id"))],
    }


def triage_incident(state: IncidentState) -> dict[str, Any]:
    started = time.perf_counter()
    alert = state["selected_alert"]
    priority = state["priority"]
    guidance = {
        "P1": "impacto critico: escalar inmediatamente al equipo responsable y contener el incidente",
        "P2": "degradacion importante: investigar ahora y definir contencion prioritaria",
        "P3": "impacto limitado: registrar, observar y planificar correccion",
    }[priority]
    triage = {
        "priority": priority,
        "guidance": guidance,
        "team": alert.get("labels", {}).get("team"),
        "runbook_url": alert.get("runbook_url"),
        "evidence": {key: alert.get(key) for key in ("id", "summary", "description", "cluster", "namespace", "service", "started_at")},
    }
    return {"triage": triage, "_traza": [_trace("triage", started, priority=priority)]}


def propose_remediation(state: IncidentState, rag: RAGProtocol) -> dict[str, Any]:
    started = time.perf_counter()
    alert = state["selected_alert"]
    question = (
        f"Incidente {state['priority']} en Kubernetes: {alert.get('summary')}. "
        f"Namespace={alert.get('namespace')}, service={alert.get('service')}. "
        "Usa la arquitectura y knowledge base recuperadas para proponer una remediacion. "
        "Devuelve pasos, YAML o kubectl como codigo, riesgos y una causa probable. "
        "No ejecutes nada."
    )
    result = rag.responder(question, top_k=5, max_tokens=700)
    remediation = {
        "status": "proposed_not_executed",
        "question": question,
        "proposal": result.get("respuesta", ""),
        "contexts": result.get("contextos", []),
        "model": result.get("modelo"),
    }
    return {
        "remediation": remediation,
        "_traza": [_trace("propose_remediation", started, result, status=remediation["status"])],
    }


def approve_remediation(state: IncidentState) -> dict[str, Any]:
    """Pausa antes de cualquier futura ejecucion de codigo de remediacion."""
    started = time.perf_counter()
    decision = interrupt({
        "type": "human_approval_required",
        "incident_id": state["incident_id"],
        "priority": state["priority"],
        "alert": state["selected_alert"],
        "remediation": state["remediation"],
        "message": "Aprueba explicitamente la propuesta. Este grafo no ejecuta codigo automaticamente.",
    })
    approved = bool(decision) if not isinstance(decision, dict) else bool(decision.get("approved"))
    approval = {
        "approved": approved,
        "decision": decision,
        "status": "approved_not_executed" if approved else "rejected_not_executed",
    }
    return {"approval": approval, "_traza": [_trace("approve_remediation", started, approved=approved)]}


def post_incident_review(state: IncidentState, h200: Any) -> dict[str, Any]:
    started = time.perf_counter()
    approval = state["approval"]
    alert = state["selected_alert"]
    prompt = (
        "Genera un Post-Incident Review en espanol y en formato JSON con las claves "
        "timeline, priority, solution, rca, what_worked, what_failed y preventive_actions. "
        "No inventes datos; marca como hipotetico lo que no este demostrado.\n\n"
        f"Alerta: {json.dumps(alert, ensure_ascii=False)}\n"
        f"Triage: {json.dumps(state['triage'], ensure_ascii=False)}\n"
        f"Remediacion propuesta: {json.dumps(state['remediation'], ensure_ascii=False)}\n"
        f"Decision humana: {json.dumps(approval, ensure_ascii=False)}"
    )
    result = h200.chat([
        {"role": "system", "content": "Eres un SRE que documenta incidentes con precision."},
        {"role": "user", "content": prompt},
    ], json_mode=True, max_tokens=900)
    try:
        review = json.loads(result["contenido"])
    except (json.JSONDecodeError, TypeError):
        review = {"raw": result.get("contenido", ""), "parse_error": True}
    actions = review.get("preventive_actions", []) if isinstance(review, dict) else []
    return {
        "review": review,
        "preventive_actions": actions if isinstance(actions, list) else [str(actions)],
        "_traza": [_trace("post_incident_review", started, result, approved=approval["approved"])],
    }


def record_incident(state: IncidentState, memory: IncidentMemory) -> dict[str, Any]:
    started = time.perf_counter()
    historical = memory.find_similar(state["selected_alert"])
    memory.save(state)
    learned = [
        action
        for incident in historical
        for action in incident.get("preventive_actions", [])
        if action not in state.get("preventive_actions", [])
    ]
    return {
        "historical_incidents": historical,
        "preventive_actions": state.get("preventive_actions", []) + learned,
        "_traza": [_trace("record_incident", started, historical_count=len(historical), persisted=True)],
    }


def route_after_detection(state: IncidentState) -> str:
    return "triage" if state.get("selected_alert") else "end"


def build_graph(telemetry: TelemetryClient | None = None, rag: RAGProtocol | None = None,
                h200: Any | None = None, memory: IncidentMemory | None = None):
    """Construye el grafo con dependencias inyectadas y checkpointer externo."""
    telemetry = telemetry or LocalTelemetryClient()
    if rag is None:
        rag = RagTaller03()
        rag.indexar()
    h200 = h200 or getattr(rag, "cliente", None)
    if h200 is None:
        raise ValueError("Se necesita h200 o un rag con cliente H200")
    memory = memory or IncidentMemory()

    graph = StateGraph(IncidentState)
    graph.add_node("detect_telemetry", lambda state: detect_telemetry(state, telemetry))
    graph.add_node("triage", triage_incident)
    graph.add_node("propose_remediation", lambda state: propose_remediation(state, rag))
    graph.add_node("approve_remediation", approve_remediation)
    graph.add_node("post_incident_review", lambda state: post_incident_review(state, h200))
    graph.add_node("record_incident", lambda state: record_incident(state, memory))
    graph.add_edge(START, "detect_telemetry")
    graph.add_conditional_edges("detect_telemetry", route_after_detection, {"triage": "triage", "end": END})
    graph.add_edge("triage", "propose_remediation")
    graph.add_edge("propose_remediation", "approve_remediation")
    graph.add_edge("approve_remediation", "post_incident_review")
    graph.add_edge("post_incident_review", "record_incident")
    graph.add_edge("record_incident", END)
    return graph.compile(checkpointer=InMemorySaver())


__all__ = [
    "IncidentMemory",
    "IncidentState",
    "LocalTelemetryClient",
    "build_graph",
]