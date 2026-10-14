"""Incident Commander con LangGraph, RAG, aprobacion humana y memoria SQLite."""

from __future__ import annotations

import json
import operator
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from taller04.rag_taller04 import RagTaller04


PROJECT_DIR = Path(__file__).resolve().parents[2]
MEMORY_PATH = PROJECT_DIR / "output_data" / "incident_memory.sqlite3"
Priority = Literal["P1", "P2", "P3"]


class IncidentState(TypedDict, total=False):
    incident_id: str
    alerts: list[dict[str, Any]]
    selected_alert: dict[str, Any]
    priority: Priority
    triage: dict[str, Any]
    rag_contexts: list[dict[str, Any]]
    remediation: dict[str, Any]
    reflection: dict[str, Any]
    judge: dict[str, Any]
    policy: dict[str, Any]
    approval: dict[str, Any]
    execution: dict[str, Any]
    review: dict[str, Any]
    preventive_actions: list[str]
    historical_incidents: list[dict[str, Any]]
    _traza: Annotated[list[dict[str, Any]], operator.add]


class RAGProtocol(Protocol):
    def recuperar(self, pregunta: str, top_k: int = 5) -> list[dict[str, Any]]: ...

    def responder(self, pregunta: str, top_k: int = 5, max_tokens: int = 512) -> dict[str, Any]: ...


class JudgeProtocol(Protocol):
    def chat(self, mensajes: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]: ...


class ExecutorProtocol(Protocol):
    def execute(self, actions: list[dict[str, str]]) -> dict[str, Any]: ...


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
        from taller04.telemetry_mcp import list_alerts

        return list_alerts(status="firing")


def _trace(node: str, started: float, result: dict[str, Any] | None = None,
           **details: Any) -> dict[str, Any]:
    usage = (result or {}).get("uso")
    latency = (result or {}).get("latencia_s")
    return {
        "nodo": node,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latencia_s": round(latency if latency is not None else time.perf_counter() - started, 6),
        "tokens_entrada": usage.get("prompt_tokens") if usage else None,
        "tokens_salida": usage.get("completion_tokens") if usage else None,
        "tokens_status": "measured" if usage else "not_applicable_no_llm_call",
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
    candidate = alerts[0]
    incident_id = f"incident-pending-{uuid.uuid4().hex[:8]}"
    return {
        "incident_id": incident_id,
        "alerts": alerts,
        "selected_alert": candidate,
        "priority": _priority(candidate),
        "_traza": [_trace(
            "detect_telemetry", started, alert_count=len(alerts), alert_id=candidate.get("id"),
            competing_alerts=len(alerts), selection_reason="candidate forwarded to triage agent",
        )],
    }


def triage_incident(state: IncidentState, h200: JudgeProtocol) -> dict[str, Any]:
    started = time.perf_counter()
    assessment_prompt = (
        "Eres el agente de triage de incidentes Kubernetes. Revisa todas las alertas observadas, "
        "prioriza por severidad y evalua impacto operacional a partir de summary, description, "
        "cluster, namespace, service, labels y antiguedad. No inventes metricas ausentes. "
        "Devuelve solo JSON con selected_alert_id, priority P1/P2/P3, impact_score de 0 a 100, "
        "rationale, guidance y ranked_alerts. ranked_alerts debe contener una entrada para "
        "cada alerta con alert_id, priority, impact_score, rationale y rank.\n"
        f"Alertas observadas: {json.dumps(state.get('alerts', []), ensure_ascii=False)}"
    )
    result = h200.chat([
        {"role": "system", "content": "Clasificas incidentes y justificas decisiones operativas."},
        {"role": "user", "content": assessment_prompt},
    ], json_mode=True, max_tokens=500)
    try:
        assessment = json.loads(result.get("contenido", ""))
    except (json.JSONDecodeError, TypeError):
        assessment = {"selected_alert_id": state["selected_alert"].get("id"),
                      "priority": state["priority"], "impact_score": None,
                      "rationale": "Triage model returned invalid JSON; candidate retained.",
                      "guidance": "Escalate for operator review."}
    selected_id = assessment.get("selected_alert_id")
    alert = next((item for item in state["alerts"] if item.get("id") == selected_id), state["selected_alert"])
    priority = assessment.get("priority") if assessment.get("priority") in ("P1", "P2", "P3") else _priority(alert)
    guidance = {
        "P1": "impacto critico: escalar inmediatamente al equipo responsable y contener el incidente",
        "P2": "degradacion importante: investigar ahora y definir contencion prioritaria",
        "P3": "impacto limitado: registrar, observar y planificar correccion",
    }[priority]
    triage = {
        "priority": priority,
        "guidance": assessment.get("guidance") or guidance,
        "impact_score": assessment.get("impact_score"),
        "rationale": assessment.get("rationale"),
        "ranked_alerts": assessment.get("ranked_alerts", []),
        "model_assessment": assessment,
        "team": alert.get("labels", {}).get("team"),
        "runbook_url": alert.get("runbook_url"),
        "evidence": {key: alert.get(key) for key in ("id", "summary", "description", "cluster", "namespace", "service", "started_at")},
    }
    return {"selected_alert": alert, "priority": priority, "incident_id": f"incident-{alert.get('id')}",
            "triage": triage, "_traza": [_trace("triage", started, result, priority=priority,
                                                    competing_alerts=len(state.get("alerts", [])),
                                                    selection_reason="LLM evaluated alert evidence and impact")]}


def _remediation_question(state: IncidentState) -> str:
    alert = state["selected_alert"]
    return (
        f"Incidente {state['priority']} en Kubernetes: {alert.get('summary')}. "
        f"Namespace={alert.get('namespace')}, service={alert.get('service')}. "
        "Usa la arquitectura y knowledge base recuperadas para proponer una remediacion. "
        "Devuelve pasos, YAML o kubectl como codigo, riesgos y una causa probable. "
        "No ejecutes nada."
    )


def retrieve_rag(state: IncidentState, rag: RAGProtocol) -> dict[str, Any]:
    started = time.perf_counter()
    contexts = rag.recuperar(_remediation_question(state), top_k=5)
    return {
        "rag_contexts": contexts,
        "_traza": [_trace("retrieve_rag", started, context_count=len(contexts),
                           metric_note="embedding latency measured; token usage not returned by embeddings endpoint")],
    }


def propose_remediation(state: IncidentState, rag: RAGProtocol) -> dict[str, Any]:
    started = time.perf_counter()
    question = _remediation_question(state)
    contexts = state.get("rag_contexts", [])
    if hasattr(rag, "cliente"):
        prompt = RagTaller04.construir_prompt(question, contexts)
        result = rag.cliente.chat([
            {"role": "system", "content": "Eres un experto en Kubernetes y remediacion segura. No ejecutes nada."},
            {"role": "user", "content": prompt},
        ], max_tokens=700)
        result = {"respuesta": result.get("contenido", ""), "contextos": contexts,
                  "modelo": getattr(rag.cliente, "modelo", None), "uso": result.get("uso", {}),
                  "latencia_s": result.get("latencia_s", 0.0)}
    else:
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
        "_traza": [_trace("propose_remediation", started, result,
                   status=remediation["status"], context_count=len(contexts))],
    }


def _json_review(client: JudgeProtocol, prompt: str) -> dict[str, Any]:
    result = client.chat([{"role": "system", "content": "Devuelve solo JSON valido y no ejecutes acciones."},
                          {"role": "user", "content": prompt}], json_mode=True, max_tokens=700)
    try:
        return json.loads(result.get("contenido", ""))
    except (json.JSONDecodeError, TypeError):
        return {"valid": False, "error": "judge_returned_invalid_json", "raw": result.get("contenido", "")}


def self_reflect(state: IncidentState, h200: JudgeProtocol) -> dict[str, Any]:
    started = time.perf_counter()
    review = _json_review(h200, (
        "Revisa esta propuesta de remediacion Kubernetes antes de cualquier ejecucion. "
        "Evalua evidencia suficiente, reversibilidad, riesgo y datos faltantes. Devuelve "
        "JSON con valid, ready, risks, missing_evidence y recommended_changes.\n"
        f"Alerta: {json.dumps(state['selected_alert'], ensure_ascii=False)}\n"
        f"Propuesta: {json.dumps(state['remediation'], ensure_ascii=False)}"
    ))
    return {"reflection": review, "_traza": [_trace("self_reflect", started, reflection_valid=review.get("valid", False))]}


def external_judge(state: IncidentState, judge: JudgeProtocol) -> dict[str, Any]:
    started = time.perf_counter()
    review = _json_review(judge, (
        "Actua como juez externo de seguridad SRE. No ejecutes comandos. Evalua de forma "
        "independiente si la propuesta coincide con la alerta, es segura y es reversible. "
        "Devuelve JSON con valid, score entre 0 y 1, allow_recommendation, findings y required_changes.\n"
        f"Triage: {json.dumps(state['triage'], ensure_ascii=False)}\n"
        f"Reflexion previa: {json.dumps(state.get('reflection', {}), ensure_ascii=False)}\n"
        f"Propuesta: {json.dumps(state['remediation'], ensure_ascii=False)}"
    ))
    return {"judge": review, "_traza": [_trace("external_judge", started, judge_valid=review.get("valid", False))]}


def policy_gate(state: IncidentState) -> dict[str, Any]:
    """Valida sin LLM que solo acciones kubectl estructuradas y no destructivas pasen."""
    started = time.perf_counter()
    proposal = state["remediation"].get("proposal", "")
    commands = [line.strip() for line in proposal.splitlines() if line.strip().startswith("kubectl ")]
    forbidden = ("|", ";", "&&", "||", ">", "<", "$", "`", " rm ", " delete ", " apply ")
    actions = []
    issues = []
    for command in commands:
        if any(token in command for token in forbidden):
            issues.append("shell_or_destructive_operator")
            continue
        match = re.fullmatch(r"kubectl -n ([a-z0-9-]+) rollout restart deployment/([a-z0-9-]+)", command)
        if match:
            actions.append({"kind": "rollout_restart", "namespace": match.group(1), "deployment": match.group(2)})
        else:
            issues.append("command_not_allowlisted")
    judge = state.get("judge", {})
    reflection = state.get("reflection", {})
    allowed = bool(actions) and not issues and judge.get("valid") is True and float(judge.get("score", 0)) >= 0.85 and reflection.get("ready") is True
    policy = {"allowed": allowed, "actions": actions, "issues": sorted(set(issues)),
              "reason": "passed_deterministic_allowlist" if allowed else "blocked_by_policy"}
    return {"policy": policy, "_traza": [_trace("policy_gate", started, allowed=allowed, action_count=len(actions))]}


def auto_approve(state: IncidentState) -> dict[str, Any]:
    started = time.perf_counter()
    return {"approval": {"approved": True, "status": "autonomous_policy_approved",
                          "judge_score": state["judge"].get("score"), "policy": state["policy"]},
            "_traza": [_trace("auto_approve", started, approved=True, mode="autonomous_opt_in")]}


def policy_reject(state: IncidentState) -> dict[str, Any]:
    started = time.perf_counter()
    return {"approval": {"approved": False, "status": "autonomous_policy_rejected",
                          "policy": state["policy"]},
            "_traza": [_trace("policy_reject", started, approved=False, mode="autonomous_opt_in")]}


def execute_remediation(state: IncidentState, executor: ExecutorProtocol | None) -> dict[str, Any]:
    started = time.perf_counter()
    if not state.get("approval", {}).get("approved"):
        result = {"status": "not_executed", "reason": "not_approved"}
    elif executor is None:
        result = {"status": "not_executed", "reason": "executor_not_configured", "actions": state["policy"].get("actions", [])}
    else:
        result = executor.execute(state["policy"].get("actions", []))
    return {"execution": result, "_traza": [_trace("execute_remediation", started, execution_status=result.get("status"))]}


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
        "Genera un Post-Incident Review profesional en espanol y en formato JSON con las claves "
        "incident_id, executive_summary, impact, detection, timeline, response, resolution, "
        "rca, lessons_learned y action_items. La clave rca debe contener summary, root_cause, "
        "confidence, contributing_factors y five_whys, una lista de cinco objetos con why, "
        "finding y evidence. Cada action_items debe contener id, action, owner, priority, "
        "due, status. Incluye tambien preventive_actions como lista de acciones resumidas. "
        "No inventes datos; marca como hipotetico lo que no este demostrado.\n\n"
        f"Incident ID: {state['incident_id']}\n"
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
    return "triage" if state.get("alerts") else "end"


def build_graph(telemetry: TelemetryClient | None = None, rag: RAGProtocol | None = None,
                h200: Any | None = None, memory: IncidentMemory | None = None,
                judge: JudgeProtocol | None = None, executor: ExecutorProtocol | None = None,
                autonomous: bool = False):
    """Construye el grafo con dependencias inyectadas y checkpointer externo."""
    telemetry = telemetry or LocalTelemetryClient()
    if rag is None:
        rag = RagTaller04()
        rag.indexar()
    h200 = h200 or getattr(rag, "cliente", None)
    if h200 is None:
        raise ValueError("Se necesita h200 o un rag con cliente H200")
    memory = memory or IncidentMemory()
    judge = judge or h200

    graph = StateGraph(IncidentState)
    graph.add_node("detect_telemetry", lambda state: detect_telemetry(state, telemetry))
    graph.add_node("triage", lambda state: triage_incident(state, h200))
    graph.add_node("retrieve_rag", lambda state: retrieve_rag(state, rag))
    graph.add_node("propose_remediation", lambda state: propose_remediation(state, rag))
    graph.add_node("self_reflect", lambda state: self_reflect(state, h200))
    graph.add_node("external_judge", lambda state: external_judge(state, judge))
    graph.add_node("policy_gate", policy_gate)
    graph.add_node("approve_remediation", approve_remediation)
    graph.add_node("auto_approve", auto_approve)
    graph.add_node("policy_reject", policy_reject)
    graph.add_node("execute_remediation", lambda state: execute_remediation(state, executor))
    graph.add_node("post_incident_review", lambda state: post_incident_review(state, h200))
    graph.add_node("record_incident", lambda state: record_incident(state, memory))
    graph.add_edge(START, "detect_telemetry")
    graph.add_conditional_edges("detect_telemetry", route_after_detection, {"triage": "triage", "end": END})
    graph.add_edge("triage", "retrieve_rag")
    graph.add_edge("retrieve_rag", "propose_remediation")
    graph.add_edge("propose_remediation", "self_reflect")
    graph.add_edge("self_reflect", "external_judge")
    graph.add_edge("external_judge", "policy_gate")

    def route_policy(state: IncidentState) -> str:
        if autonomous:
            return "auto_approve" if state.get("policy", {}).get("allowed") else "policy_reject"
        return "human_approval"

    graph.add_conditional_edges("policy_gate", route_policy,
                                {"human_approval": "approve_remediation",
                                 "auto_approve": "auto_approve",
                                 "policy_reject": "policy_reject"})
    graph.add_edge("approve_remediation", "execute_remediation")
    graph.add_edge("auto_approve", "execute_remediation")
    graph.add_edge("policy_reject", "execute_remediation")
    graph.add_edge("execute_remediation", "post_incident_review")
    graph.add_edge("post_incident_review", "record_incident")
    graph.add_edge("record_incident", END)
    return graph.compile(checkpointer=InMemorySaver())


__all__ = [
    "IncidentMemory",
    "IncidentState",
    "LocalTelemetryClient",
    "build_graph",
]