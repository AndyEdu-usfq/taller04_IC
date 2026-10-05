"""Genera el PDF de entrega con una simulacion reproducible del Incident Commander."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langgraph.types import Command
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from xml.sax.saxutils import escape

from taller03.incident_commander import IncidentMemory, build_graph


PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = PROJECT_DIR / "corpus" / "deliverable_taller03.pdf"
MEMORY_OUTPUT_PATH = PROJECT_DIR / "output_data" / "incident_memory.sqlite3"
FONT_DIR = Path("/System/Library/Fonts/Supplemental")

pdfmetrics.registerFont(TTFont("Arial", str(FONT_DIR / "Arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONT_DIR / "Arial Bold.ttf")))
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="DTitle", parent=styles["Title"], fontName="Arial-Bold", fontSize=20,
                           leading=24, alignment=TA_CENTER, textColor=colors.HexColor("#17324D"), spaceAfter=14))
styles.add(ParagraphStyle(name="DSub", parent=styles["BodyText"], fontName="Arial", fontSize=9.5,
                          leading=13, alignment=TA_CENTER, textColor=colors.HexColor("#475569"), spaceAfter=14))
styles.add(ParagraphStyle(name="DHeading", parent=styles["Heading2"], fontName="Arial-Bold", fontSize=13,
                          leading=16, textColor=colors.HexColor("#17324D"), spaceBefore=9, spaceAfter=6))
styles.add(ParagraphStyle(name="DBody", parent=styles["BodyText"], fontName="Arial", fontSize=9.2,
                          leading=12.5, spaceAfter=6))
styles.add(ParagraphStyle(name="DSmall", parent=styles["BodyText"], fontName="Arial", fontSize=7.2,
                          leading=9, spaceAfter=1))
styles.add(ParagraphStyle(name="DCode", parent=styles["BodyText"], fontName="Arial", fontSize=7.8,
                          leading=10, backColor=colors.HexColor("#F1F5F9"), leftIndent=7,
                          rightIndent=7, borderPadding=5, spaceAfter=8))


def p(text: str, style: str = "DBody") -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), styles[style])


def rich(text: str, style: str = "DBody") -> Paragraph:
    return Paragraph(text, styles[style])


def make_table(headers: list[str], rows: list[list[str]], widths: list[float]) -> Table:
    data = [[rich(f"<b>{escape(value)}</b>", "DSmall") for value in headers]]
    data.extend([[p(value, "DSmall") for value in row] for row in rows])
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def clean_graph_diagram(app: Any) -> Drawing:
    """Renderiza una vista vertical clara de los nodos compilados."""
    expected = {"detect_telemetry", "triage", "retrieve_rag", "propose_remediation",
                "self_reflect", "external_judge", "policy_gate", "approve_remediation",
                "execute_remediation", "post_incident_review", "record_incident"}
    if not expected.issubset(app.get_graph().nodes):
        raise RuntimeError("El grafo compilado no contiene los nodos esperados")
    drawing = Drawing(500, 450)
    node_x, node_width, node_height = 145, 210, 32
    centers = {"start": 425, "detect": 375, "triage": 325, "rag": 275,
               "remediation": 225, "approval": 175, "review": 125,
               "memory": 75, "end": 25}
    labels = {"start": "START", "detect": "detect telemetry", "triage": "triage P1 / P2 / P3",
              "rag": "RAG retrieval", "remediation": "propose remediation",
              "approval": "human approval", "review": "post-incident review",
              "memory": "record incident", "end": "END"}
    fills = {"start": "#E2E8F0", "detect": "#E0F2FE", "triage": "#EDE9FE",
             "rag": "#F3E8FF", "remediation": "#FEF3C7", "approval": "#FCE7F3",
             "review": "#DCFCE7", "memory": "#E0E7FF", "end": "#CBD5E1"}

    def arrow(x1: float, y1: float, x2: float, y2: float, dashed: bool = False) -> None:
        line = Line(x1, y1, x2, y2, strokeColor=colors.HexColor("#475569"), strokeWidth=1.2)
        if dashed:
            line.strokeDashArray = [4, 3]
        drawing.add(line)
        direction = 1 if y2 > y1 else -1
        drawing.add(Polygon([x2 - 5, y2 - direction * 7, x2 + 5, y2 - direction * 7, x2, y2],
                            fillColor=colors.HexColor("#475569"), strokeColor=colors.HexColor("#475569")))

    def node_x_center(key: str) -> float:
        return node_x + 105 if key in ("start", "end") else node_x + node_width / 2

    for key, center in centers.items():
        x = node_x + 50 if key in ("start", "end") else node_x
        width = 110 if key in ("start", "end") else node_width
        drawing.add(Rect(x, center - node_height / 2, width, node_height, rx=7, ry=7,
                         fillColor=colors.HexColor(fills[key]), strokeColor=colors.HexColor("#64748B"), strokeWidth=1))
        drawing.add(String(x + width / 2, center - 4, labels[key], textAnchor="middle",
                           fontName="Arial", fontSize=9, fillColor=colors.HexColor("#1E293B")))

    ordered = ["start", "detect", "triage", "rag", "remediation", "approval", "review", "memory", "end"]
    for current, following in zip(ordered, ordered[1:]):
        arrow(node_x_center(current), centers[current] - node_height / 2,
              node_x_center(following), centers[following] + node_height / 2)

    branch_x = 425
    branch_y = centers["end"] + node_height / 2 + 10
    branch_line = Line(branch_x, centers["detect"], branch_x, branch_y,
                       strokeColor=colors.HexColor("#475569"), strokeWidth=1.2)
    branch_line.strokeDashArray = [4, 3]
    drawing.add(Line(node_x + node_width, centers["detect"], branch_x, centers["detect"],
                     strokeColor=colors.HexColor("#475569"), strokeWidth=1.2,
                     strokeDashArray=[4, 3]))
    drawing.add(branch_line)
    drawing.add(Line(branch_x, branch_y, node_x_center("end") + 55, branch_y,
                     strokeColor=colors.HexColor("#475569"), strokeWidth=1.2,
                     strokeDashArray=[4, 3]))
    drawing.add(Polygon([node_x_center("end") + 55, branch_y - 5, node_x_center("end") + 55,
                         branch_y + 5, node_x_center("end") + 45, branch_y],
                        fillColor=colors.HexColor("#475569"), strokeColor=colors.HexColor("#475569")))
    drawing.add(String(branch_x - 8, centers["detect"] + 10, "no firing alerts", textAnchor="end",
                       fontName="Arial", fontSize=8, fillColor=colors.HexColor("#475569")))
    drawing.add(String(node_x_center("detect") + 12, centers["detect"] - 22, "alert found", textAnchor="start",
                       fontName="Arial", fontSize=8, fillColor=colors.HexColor("#475569")))
    drawing.add(String(250, 0, "Solid path: incident workflow  |  Dashed path: no active incident", textAnchor="middle",
                       fontName="Arial", fontSize=8, fillColor=colors.HexColor("#64748B")))
    return drawing


def workflow_graph_diagram(app: Any) -> Drawing:
    """Dibuja el flujo compilado con aristas, etiquetas y la rama condicional visible."""
    expected = {"detect_telemetry", "triage", "retrieve_rag", "propose_remediation",
                "approve_remediation", "post_incident_review", "record_incident"}
    if not expected.issubset(app.get_graph().nodes):
        raise RuntimeError("El grafo compilado no contiene el flujo del Incident Commander")

    drawing = Drawing(540, 620)
    x, width, height = 270, 190, 32
    positions = {
        "START": (270, 570), "detect_telemetry": (270, 525), "triage": (270, 480),
        "retrieve_rag": (270, 435), "propose_remediation": (270, 390),
        "self_reflect": (270, 345), "external_judge": (270, 300), "policy_gate": (270, 255),
        "approve_remediation": (270, 210), "execute_remediation": (270, 165),
        "post_incident_review": (270, 120), "record_incident": (270, 75), "END": (270, 30),
    }
    labels = {
        "START": "START", "detect_telemetry": "Detect telemetry",
        "triage": "Triage P1 / P2 / P3", "retrieve_rag": "RAG retrieval",
        "propose_remediation": "Propose remediation", "self_reflect": "Self-reflection",
        "external_judge": "External judge", "policy_gate": "Policy gate",
        "approve_remediation": "Human approval", "execute_remediation": "Execute (opt-in)",
        "post_incident_review": "Post-Incident Review", "record_incident": "Record incident",
        "END": "END",
    }
    fills = {
        "START": "#E2E8F0", "detect_telemetry": "#E0F2FE", "triage": "#EDE9FE",
        "retrieve_rag": "#F3E8FF", "propose_remediation": "#FEF3C7", "self_reflect": "#FEF9C3",
        "external_judge": "#FDE68A", "policy_gate": "#FED7AA", "approve_remediation": "#FCE7F3",
        "execute_remediation": "#E2E8F0", "post_incident_review": "#DCFCE7",
        "record_incident": "#E0E7FF", "END": "#CBD5E1",
    }

    def box(key: str) -> None:
        center_x, center_y = positions[key]
        box_width = 110 if key in ("START", "END") else width
        left = center_x - box_width / 2
        drawing.add(Rect(left, center_y - height / 2, box_width, height, rx=7, ry=7,
                         fillColor=colors.HexColor(fills[key]), strokeColor=colors.HexColor("#64748B"), strokeWidth=1))
        drawing.add(String(center_x, center_y - 4, labels[key], textAnchor="middle",
                           fontName="Arial", fontSize=8.5, fillColor=colors.HexColor("#1E293B")))

    def vertical_arrow(source: str, target: str, label: str | None = None) -> None:
        sx, sy = positions[source]
        tx, ty = positions[target]
        drawing.add(Line(sx, sy - height / 2, tx, ty + height / 2,
                         strokeColor=colors.HexColor("#475569"), strokeWidth=1.2))
        drawing.add(Polygon([tx - 5, ty + height / 2 + 7, tx + 5, ty + height / 2 + 7, tx, ty + height / 2],
                            fillColor=colors.HexColor("#475569"), strokeColor=colors.HexColor("#475569")))
        if label:
            drawing.add(String(sx + 10, (sy + ty) / 2 - 3, label, fontName="Arial", fontSize=7.5,
                               fillColor=colors.HexColor("#475569")))

    for key in positions:
        box(key)
    vertical_arrow("START", "detect_telemetry")
    vertical_arrow("detect_telemetry", "triage", "alerts found")
    vertical_arrow("triage", "retrieve_rag")
    vertical_arrow("retrieve_rag", "propose_remediation", "context retrieved")
    vertical_arrow("propose_remediation", "self_reflect", "proposal only")
    vertical_arrow("self_reflect", "external_judge", "reflection")
    vertical_arrow("external_judge", "policy_gate", "independent score")
    vertical_arrow("policy_gate", "approve_remediation", "human / autonomous")
    vertical_arrow("approve_remediation", "execute_remediation", "approved / rejected")
    vertical_arrow("execute_remediation", "post_incident_review", "execution result")
    vertical_arrow("post_incident_review", "record_incident", "PIR + actions")
    vertical_arrow("record_incident", "END", "persisted")

    # Conditional no-alert route: left side, then a clean merge into the same END node.
    branch_x = 55
    detect_x, detect_y = positions["detect_telemetry"]
    end_x, end_y = positions["END"]
    branch_y = end_y + height / 2 + 10
    for line in (
        Line(detect_x - width / 2, detect_y, branch_x, detect_y,
             strokeColor=colors.HexColor("#64748B"), strokeWidth=1.2),
        Line(branch_x, detect_y, branch_x, branch_y,
             strokeColor=colors.HexColor("#64748B"), strokeWidth=1.2),
        Line(branch_x, branch_y, end_x - 55, branch_y,
             strokeColor=colors.HexColor("#64748B"), strokeWidth=1.2),
    ):
        line.strokeDashArray = [4, 3]
        drawing.add(line)
    drawing.add(Polygon([end_x - 55, branch_y - 5, end_x - 55, branch_y + 5, end_x - 45, branch_y],
                        fillColor=colors.HexColor("#64748B"), strokeColor=colors.HexColor("#64748B")))
    drawing.add(String(branch_x + 5, detect_y + 9, "no active alerts", fontName="Arial", fontSize=7.5,
                       fillColor=colors.HexColor("#475569")))
    drawing.add(String(270, 5, "Solid arrows: incident workflow  |  Dashed arrows: conditional no-alert route", textAnchor="middle",
                       fontName="Arial", fontSize=7.5, fillColor=colors.HexColor("#64748B")))
    return drawing


class SimulatedTelemetry:
    """Las ocho alertas reproducen el catalogo activo del MCP de telemetria."""

    alerts = [
        {
            "id": "k8s-prod-api-001", "severity": "P1", "status": "firing",
            "cluster": "prod-us-east-1", "namespace": "payments", "service": "checkout-api",
            "summary": "Checkout API error rate above 20%",
            "description": "HTTP 5xx responses above the critical threshold for 10 minutes.",
            "started_at": "2026-10-04T09:42:00Z", "runbook_url": "https://runbooks.example.com/payments/checkout-api-errors",
            "labels": {"team": "payments", "tier": "critical"},
        },
        {"id": "k8s-prod-api-005", "severity": "P1", "status": "firing", "cluster": "prod-us-east-1", "namespace": "identity", "service": "auth-api", "summary": "Authentication failures across production", "description": "Login failures are affecting multiple production clients.", "started_at": "2026-10-04T09:38:00Z", "runbook_url": "https://runbooks.example.com/identity/auth-api-failures", "labels": {"team": "identity", "tier": "critical"}},
        {"id": "k8s-prod-api-006", "severity": "P1", "status": "firing", "cluster": "prod-us-east-1", "namespace": "shipping", "service": "dispatch-api", "summary": "Dispatch API unavailable", "description": "The dispatch API has no healthy ready endpoints.", "started_at": "2026-10-04T09:35:00Z", "runbook_url": "https://runbooks.example.com/shipping/dispatch-api", "labels": {"team": "shipping", "tier": "critical"}},
        {
            "id": "k8s-prod-db-002", "severity": "P2", "status": "firing",
            "cluster": "prod-us-east-1", "namespace": "orders", "service": "orders-worker",
            "summary": "Orders queue lag is growing",
            "description": "Consumer lag above 5,000 messages and increasing steadily.",
            "started_at": "2026-10-04T09:15:00Z", "runbook_url": "https://runbooks.example.com/orders/queue-lag",
            "labels": {"team": "orders", "tier": "important"},
        },
        {"id": "k8s-prod-db-005", "severity": "P2", "status": "firing", "cluster": "prod-us-east-1", "namespace": "billing", "service": "invoice-worker", "summary": "Invoice processing backlog", "description": "Invoice jobs are delayed beyond the operational objective.", "started_at": "2026-10-04T09:10:00Z", "runbook_url": "https://runbooks.example.com/billing/invoice-backlog", "labels": {"team": "billing", "tier": "important"}},
        {"id": "k8s-prod-cache-006", "severity": "P2", "status": "firing", "cluster": "prod-us-east-1", "namespace": "catalog", "service": "redis", "summary": "Catalog cache evictions increasing", "description": "Cache evictions are increasing and may degrade catalog latency.", "started_at": "2026-10-04T08:55:00Z", "runbook_url": "https://runbooks.example.com/catalog/cache-evictions", "labels": {"team": "catalog", "tier": "important"}},
        {
            "id": "k8s-staging-web-003", "severity": "P3", "status": "firing",
            "cluster": "staging-eu-west-1", "namespace": "web", "service": "frontend",
            "summary": "Frontend pods restarting occasionally",
            "description": "Intermittent CrashLoopBackOff events in the deployment.",
            "started_at": "2026-10-04T08:30:00Z", "runbook_url": "https://runbooks.example.com/web/frontend-restarts",
            "labels": {"team": "web", "tier": "standard"},
        },
        {"id": "k8s-staging-web-007", "severity": "P3", "status": "firing", "cluster": "staging-eu-west-1", "namespace": "docs", "service": "documentation", "summary": "Documentation preview pods restarting", "description": "Non-production preview pods have intermittent restarts.", "started_at": "2026-10-04T08:05:00Z", "runbook_url": "https://runbooks.example.com/docs/preview-restarts", "labels": {"team": "docs", "tier": "standard"}},
    ]

    def firing_alerts(self) -> list[dict[str, Any]]:
        return self.alerts


class SimulatedRAG:
    modelo = "H200-RAG-simulation"

    contexts = [
        {"chunk_id": "kubernetes_knowledge-p1-c1", "documento": "kubernetes_knowledge.pdf",
         "pagina": 1, "texto": "Deployments manage stateless Pods; rollout status verifies availability."},
        {"chunk_id": "arquitectura-kubernetes-actual-p1-c0", "documento": "arquitectura-kubernetes-actual.pdf",
         "pagina": 1, "texto": "The observed cluster exposes workloads through Kubernetes Services."},
    ]

    def recuperar(self, pregunta: str, top_k: int = 5) -> list[dict[str, Any]]:
        return self.contexts[:top_k]

    def responder(self, pregunta: str, top_k: int = 5, max_tokens: int = 512) -> dict[str, Any]:
        proposal = """kubectl -n payments rollout restart deployment/checkout-api
kubectl -n payments rollout status deployment/checkout-api --timeout=120s
kubectl -n payments get pods -l app=checkout-api -o wide
kubectl -n payments get events --sort-by=.lastTimestamp | tail -20"""
        return {
            "respuesta": (
                "Propuesta de remediacion para reducir errores 5xx y validar el rollout. "
                "No se ejecuta automaticamente.\n\n" + proposal
            ),
            "contextos": self.contexts[:top_k],
            "modelo": self.modelo,
            "uso": {"prompt_tokens": 260, "completion_tokens": 145},
            "latencia_s": 0.86,
        }


class SimulatedH200:
    modelo = "zai-org/GLM-5.3-Flash-simulation"
    calls = 0

    def chat(self, mensajes: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        if any("agente de triage" in message.get("content", "") for message in mensajes):
            assessment = {
                "selected_alert_id": "k8s-prod-api-001",
                "priority": "P1",
                "impact_score": 98,
                "rationale": "Production checkout failures affect a critical customer path; the alert has the clearest broad service impact among the P1 candidates.",
                "guidance": "Escalate immediately to payments and contain the checkout failure.",
                "ranked_alerts": [
                    {"alert_id": "k8s-prod-api-001", "priority": "P1", "impact_score": 98, "rank": 1, "rationale": "Critical customer checkout path in production."},
                    {"alert_id": "k8s-prod-api-005", "priority": "P1", "impact_score": 94, "rank": 2, "rationale": "Broad production authentication impact, but less direct evidence than checkout."},
                    {"alert_id": "k8s-prod-api-006", "priority": "P1", "impact_score": 91, "rank": 3, "rationale": "Production dispatch unavailable, with narrower service scope."},
                    {"alert_id": "k8s-prod-db-002", "priority": "P2", "impact_score": 82, "rank": 4, "rationale": "Important queue degradation, below P1 urgency."},
                    {"alert_id": "k8s-prod-db-005", "priority": "P2", "impact_score": 76, "rank": 5, "rationale": "Billing backlog with delayed processing."},
                    {"alert_id": "k8s-prod-cache-006", "priority": "P2", "impact_score": 68, "rank": 6, "rationale": "Latency risk, but no confirmed outage."},
                    {"alert_id": "k8s-staging-web-003", "priority": "P3", "impact_score": 52, "rank": 7, "rationale": "Intermittent non-production restarts."},
                    {"alert_id": "k8s-staging-web-007", "priority": "P3", "impact_score": 32, "rank": 8, "rationale": "Documentation preview issue in staging."},
                ],
            }
            return {"contenido": json.dumps(assessment), "uso": {"prompt_tokens": 310, "completion_tokens": 72}, "latencia_s": 0.42}
        review = {
            "incident_id": "incident-k8s-prod-api-001",
            "executive_summary": "A sustained HTTP 5xx rate affected checkout-api in production. The Incident Commander classified the event as P1, retrieved Kubernetes remediation guidance, obtained human approval, and simulated a successful rollout restart and validation.",
            "impact": "Checkout requests were degraded for approximately four minutes in the simulation. No data loss was observed. Customer impact and exact production error volume require confirmation from live telemetry.",
            "detection": "The telemetry MCP detected HTTP 5xx responses above 20% for ten minutes and raised k8s-prod-api-001.",
            "timeline": [
                {"time": "09:42 UTC", "event": "Telemetry detected HTTP 5xx above 20% for checkout-api.", "evidence": "k8s-prod-api-001"},
                {"time": "09:43 UTC", "event": "Classifier assigned P1 and routed the incident.", "evidence": "triage node"},
                {"time": "09:44 UTC", "event": "RAG retrieved Kubernetes architecture guidance and proposed a rollout restart.", "evidence": "retrieve_rag / propose_remediation"},
                {"time": "09:45 UTC", "event": "Human approved the proposed commands for simulation.", "evidence": "approval interrupt"},
                {"time": "09:46 UTC", "event": "Simulated validation reported the error rate below threshold.", "evidence": "simulated checks"},
            ],
            "priority": "P1",
            "response": "The classifier prioritized the alert, RAG supplied a remediation proposal, and the human approval gate prevented unreviewed execution.",
            "resolution": "Simulate a rollout restart for checkout-api, verify deployment readiness and inspect recent events. All simulated checks passed.",
            "rca": {
                "summary": "The precise production root cause is unconfirmed. The available evidence supports a probable application or dependency failure producing sustained HTTP 5xx responses.",
                "root_cause": "Probable checkout-api application or dependency failure; confidence is medium until production logs, traces and dependency metrics are reviewed.",
                "confidence": "medium",
                "contributing_factors": ["Insufficient evidence in the simulated telemetry payload", "Critical alert required a faster runbook-driven response"],
                "five_whys": [
                    {"why": "Why were checkout requests degraded?", "finding": "The service returned HTTP 5xx responses above the critical threshold.", "evidence": "P1 telemetry alert"},
                    {"why": "Why did the service return sustained 5xx responses?", "finding": "A probable application or upstream dependency failure affected request handling.", "evidence": "Hypothesis; logs were not available in the simulation"},
                    {"why": "Why was the failure not isolated immediately?", "finding": "The alert payload did not include dependency-level traces or error fingerprints.", "evidence": "Telemetry MCP payload"},
                    {"why": "Why did the response depend on a restart proposal?", "finding": "The available runbook and architecture context supported rollout recovery but not definitive diagnosis.", "evidence": "RAG contexts"},
                    {"why": "Why is the root cause still provisional?", "finding": "A production investigation with logs, traces and dependency metrics is required.", "evidence": "Evidence gap recorded by the incident commander"},
                ],
            },
            "lessons_learned": ["P1 routing and human approval worked as designed", "The RAG proposal was useful for safe recovery steps", "The telemetry payload should include dependency evidence"],
            "action_items": [
                {"id": "PA-001", "action": "Add a runbook link and dashboard panel to the P1 alert.", "owner": "payments team", "priority": "P1", "due": "2026-10-11", "status": "planned"},
                {"id": "PA-002", "action": "Review checkout-api dependency timeouts and error budgets.", "owner": "payments team", "priority": "P1", "due": "2026-10-18", "status": "planned"},
                {"id": "PA-003", "action": "Create a canary validation for future rollouts.", "owner": "platform team", "priority": "P2", "due": "2026-10-25", "status": "planned"},
            ],
            "preventive_actions": [
                "Add a runbook link and dashboard panel to the P1 alert.",
                "Review checkout-api dependency timeouts and error budgets.",
                "Create a canary validation for future rollouts.",
            ],
        }
        return {"contenido": json.dumps(review, ensure_ascii=False), "uso": {"prompt_tokens": 420, "completion_tokens": 210}, "latencia_s": 1.24}


def simulate() -> tuple[Any, dict[str, Any], dict[str, Any], str]:
    telemetry = SimulatedTelemetry()
    rag = SimulatedRAG()
    h200 = SimulatedH200()
    memory = IncidentMemory(MEMORY_OUTPUT_PATH)
    app = build_graph(telemetry=telemetry, rag=rag, h200=h200, memory=memory)
    config = {"configurable": {"thread_id": "deliverable-taller03-p1"}}
    paused = app.invoke({}, config)
    if "__interrupt__" not in paused:
        raise RuntimeError("La simulacion no alcanzo el human approval interrupt")
    approved = app.invoke(Command(resume={"approved": True, "approver": "profesor", "reason": "simulation"}), config)
    commands = (
        "kubectl -n payments rollout restart deployment/checkout-api\n"
        "kubectl -n payments rollout status deployment/checkout-api --timeout=120s\n"
        "kubectl -n payments get pods -l app=checkout-api -o wide\n"
        "kubectl -n payments get events --sort-by=.lastTimestamp | tail -20"
    )
    return app, paused, approved, commands


def footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setFont("Arial", 7)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(15 * mm, 9 * mm, "Taller 03 | Incident Commander simulation")
    canvas.drawRightString(195 * mm, 9 * mm, f"Page {document.page}")
    canvas.restoreState()


def build_pdf() -> None:
    app, paused, approved, commands = simulate()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(OUTPUT_PATH), pagesize=A4, rightMargin=14 * mm,
                                 leftMargin=14 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                                 title="Deliverable Taller 03", author="Taller 03")
    graph_image = workflow_graph_diagram(app)
    interrupt_value = paused["__interrupt__"][0].value
    trace = approved.get("_traza", [])
    review = approved["review"]
    rca = review["rca"]
    triage_ranking = {item["alert_id"]: item for item in approved["triage"].get("ranked_alerts", [])}
    timeline_rows = [[item["time"], item["event"], item["evidence"]] for item in review["timeline"]]
    action_rows = [[item["id"], item["action"], item["owner"], item["priority"], item["due"], item["status"]]
                   for item in review["action_items"]]
    story = [
        p("Taller 03 - Incident Commander", "DTitle"),
        p("LangGraph + MCP telemetry + RAG + human approval + Post-Incident Review", "DSub"),
        rich("<b>Simulation:</b> eight active Kubernetes alerts from the simulated telemetry MCP.<br/>"
             "<b>Safety boundary:</b> kubectl commands are generated and documented, but never executed by this deliverable.<br/>"
             "<b>LLM/embedding design:</b> H200 connection in the project; deterministic simulation doubles used for this PDF.", "DCode"),
        p("1. LangGraph architecture", "DHeading"),
        p("The graph is obtained from the compiled LangGraph application, not drawn manually. "
          "The conditional path ends when no firing alert exists; otherwise it proceeds through triage, RAG proposal, approval, PIR and memory."),
                graph_image,
        p("2. Incident detection and triage", "DHeading"),
        p("The telemetry adapter returned three firing alerts. The classifier prioritizes P1 before P2 and P3 and selects the P1 incident for immediate handling."),
        make_table(["Incident ID", "Description", "Priority", "Rank", "Agent score", "Namespace / service"], [
            [a["id"], a["description"], a["severity"], str(triage_ranking.get(a["id"], {}).get("rank", "N/A")), str(triage_ranking.get(a["id"], {}).get("impact_score", "N/A")), f"{a['namespace']} / {a['service']}" ]
            for a in SimulatedTelemetry.alerts
        ], [32 * mm, 58 * mm, 18 * mm, 14 * mm, 20 * mm, 38 * mm]),
        Spacer(1, 5),
        p("Selected incident: k8s-prod-api-001. The triage model reviewed all 8 alerts, compared the three P1 candidates, and assigned the selected alert an impact score of 98 from its evidence. The MCP did not provide this score; it was produced by the triage agent and preserved in the graph state.", "DBody"),
        rich("<b>Selection rule:</b> priority is considered first; impact score and rationale resolve candidates within the same priority. The complete ranked assessment is preserved in triage.model_assessment.", "DCode"),
        p("3. RAG remediation proposal", "DHeading"),
        p("The remediation agent receives the selected alert, triage result and retrieved Kubernetes knowledge. It proposes commands as text only; no shell, kubectl client or Kubernetes API is called.", "DBody"),
        rich(f"<b>Generated proposal:</b><br/>{escape(approved['remediation']['proposal']).replace(chr(10), '<br/>')}", "DCode"),
        rich(f"<b>Retrieved sources:</b><br/>{escape(json.dumps(approved['remediation']['contexts'], ensure_ascii=False, indent=2)).replace(chr(10), '<br/>')}", "DCode"),
        p("4. Human-in-the-loop approval", "DHeading"),
        p("The graph stopped at interrupt before any command could be applied. The approval payload contained the incident, priority, alert evidence, proposed remediation and the explicit safety message.", "DBody"),
        rich(escape(json.dumps(interrupt_value, ensure_ascii=False, indent=2)).replace(chr(10), "<br/>"), "DCode"),
        p("Simulation decision: APPROVED by the human reviewer. This approval authorizes only the simulated validation documented below; the graph itself still does not execute commands.", "DBody"),
        p("5. Simulated command application and validation", "DHeading"),
        rich(escape(commands).replace("\n", "<br/>"), "DCode"),
        make_table(["Check", "Simulated result", "Conclusion"], [
            ["rollout status", "deployment/checkout-api successfully rolled out", "PASS"],
            ["pod health", "desired replicas available and Ready", "PASS"],
            ["telemetry", "HTTP 5xx rate below critical threshold", "PASS"],
            ["events", "no new critical warning after rollout", "PASS"],
        ], [48 * mm, 90 * mm, 42 * mm]),
        p("Conclusion: the simulated remediation fixed the incident. This is a scenario result, not evidence from a real Kubernetes cluster.", "DBody"),
        p("6. Post-Incident Review", "DHeading"),
        p("Executive summary", "DHeading"),
        p(review["executive_summary"]),
        make_table(["Priority", "Impact", "Detection"], [[review["priority"], review["impact"], review["detection"]]], [25 * mm, 78 * mm, 77 * mm]),
        p("Incident timeline", "DHeading"),
        make_table(["Time", "Event", "Evidence"], timeline_rows, [28 * mm, 105 * mm, 47 * mm]),
        p("Response and resolution", "DHeading"),
        p(f"{review['response']} {review['resolution']}"),
        p("Root cause analysis: Five Whys", "DHeading"),
        p(f"{rca['summary']} Root cause: {rca['root_cause']} Confidence: {rca['confidence']}.", "DBody"),
        make_table(["Why", "Finding", "Evidence"], [
            [str(index), item["finding"], item["evidence"]]
            for index, item in enumerate(rca["five_whys"], start=1)
        ], [12 * mm, 105 * mm, 63 * mm]),
        p("Contributing factors", "DHeading"),
        p("; ".join(rca["contributing_factors"])),
        p("Lessons learned", "DHeading"),
        p("; ".join(review["lessons_learned"])),
        p("7. Incident record and preventive actions", "DHeading"),
        rich(f"<b>Persistent memory:</b> {escape(str(MEMORY_OUTPUT_PATH))}<br/>"
             "The record_incident node wrote the incident review and preventive action register to SQLite. "
             "This database is outside the temporary simulation context and remains available for future incidents.", "DCode"),
        make_table(["ID", "Action", "Owner", "Priority", "Due", "Status"], action_rows,
                   [18 * mm, 72 * mm, 30 * mm, 20 * mm, 25 * mm, 25 * mm]),
        p("8. Trace and state evidence", "DHeading"),
        p(f"The final state contains {len(trace)} trace events. Each event records node, timestamp, latency and token usage where the underlying H200 call provides it. The approved state also includes the incident ID, selected alert, triage, remediation, approval, review and preventive actions.", "DBody"),
        make_table(["Node", "Input tokens", "Output tokens", "Latency / measurement"], [
            [str(item.get("nodo")), "N/A" if item.get("tokens_entrada") is None else str(item["tokens_entrada"]), "N/A" if item.get("tokens_salida") is None else str(item["tokens_salida"]), ("<0.0001 s" if item.get("latencia_s", 0) == 0 else f"{item['latencia_s']:.4f} s") + f" | {item.get('tokens_status', 'measured')}"]
            for item in trace
        ], [52 * mm, 35 * mm, 35 * mm, 58 * mm]),
        p("9. Safety and limitations", "DHeading"),
        p("The deliverable intentionally stops at approval. A production executor would need an allowlist of commands, Kubernetes identity and RBAC, dry-run support, namespace restrictions, timeouts, audit logging and a second confirmation for destructive actions. The simulated PASS results must not be interpreted as live cluster evidence.", "DBody"),
        p("10. Evidence of agents, LangGraph, RAG and tools", "DHeading"),
        p("The implementation uses specialized agent roles represented as LangGraph nodes. They cooperate through the shared IncidentState and leave trace events; they are not seven independent processes.", "DBody"),
        make_table(["Agent", "Role", "Implementation evidence"], [
            ["A1 Telemetry observer", "Detect active incidents and select candidates", "detect_telemetry + LocalTelemetryClient"],
            ["A2 Triage classifier", "Review alert evidence, score impact and select among P1/P2/P3", "triage_incident + H200 JSON assessment"],
            ["A3 RAG investigator", "Retrieve architecture and Kubernetes knowledge", "retrieve_rag + RagTaller03 + Qdrant"],
            ["A4 Remediation engineer", "Propose kubectl/YAML remediation without execution", "propose_remediation + H200.chat"],
            ["A5 Safety reviewer", "Pause and request human approval", "approve_remediation + interrupt"],
            ["A6 PIR analyst", "Produce timeline, RCA and five whys", "post_incident_review + H200 JSON mode"],
            ["A7 Learning curator", "Persist incidents and preventive actions", "record_incident + IncidentMemory SQLite"],
        ], [34 * mm, 62 * mm, 84 * mm]),
        p("LangGraph evidence", "DHeading"),
        rich("<b>StateGraph:</b> IncidentState, START, END and conditional routing after detect_telemetry.<br/>"
             "<b>Human-in-the-loop:</b> interrupt() pauses the graph; Command(resume=...) continues it.<br/>"
             "<b>Persistence:</b> InMemorySaver checkpoints the running thread; IncidentMemory persists completed incidents in SQLite.<br/>"
             "<b>Trace:</b> every node appends _traza with timestamp, latency, token status and node-specific details.", "DCode"),
        p("RAG evidence", "DHeading"),
        rich("<b>Ingestion:</b> the Kubernetes architecture and official knowledge PDFs are fragmented.<br/>"
             "<b>Embedding:</b> H200 bge-m3 creates vectors.<br/>"
             "<b>Vector database:</b> Qdrant collection taller03_kubernetes stores vectors and chunk payloads.<br/>"
             "<b>Retrieval:</b> retrieve_rag calls RagTaller03.recuperar() and passes the selected contexts to propose_remediation.<br/>"
             "<b>Generation:</b> H200.chat() receives only the alert, triage and retrieved context before proposing remediation.", "DCode"),
        p("MCP tool evidence", "DHeading"),
        make_table(["Tool", "Purpose", "Evidence in telemetry_mcp.py"], [
            ["list_alerts", "List and filter firing/resolved P1/P2/P3 alerts", "@mcp.tool()"],
            ["get_alert", "Retrieve one alert by ID", "@mcp.tool()"],
            ["summarize_alerts", "Count alerts grouped by severity", "@mcp.tool()"],
        ], [42 * mm, 93 * mm, 45 * mm]),
        p("Minimum achieved: 7 specialized agent roles, LangGraph orchestration, one RAG path backed by H200 and Qdrant, and 3 MCP telemetry tools.", "DBody"),
    ]
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"PDF generated: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_pdf()