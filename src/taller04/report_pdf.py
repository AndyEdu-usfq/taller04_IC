"""Informe legible con tablas; todas las cifras llegan de artefactos medidos."""
from __future__ import annotations
import csv,json,statistics
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether
from reportlab.graphics.shapes import Drawing,Rect,String,Line,Polygon
from .simulator import ROOT
from .guardrails import mask


def graph_drawing(source_path):
    # Build the picture from the actual Mermaid graph artifact, not a separate architecture.
    import re
    source=Path(source_path).read_text()
    edges=re.findall(r'^\s*(\w+) --> (\w+);',source,re.M)
    node_ids=set(x for edge in edges for x in edge);order=[];remaining=set(node_ids)
    while remaining:
        ready=sorted(n for n in remaining if not any(b==n and a in remaining for a,b in edges))
        if not ready:raise ValueError('Grafo inesperado')
        order+=ready;remaining-=set(ready)
    d=Drawing(510,len(order)*38+10)
    for i,name in enumerate(order):
        y=d.height-35-i*38
        d.add(Rect(120,y,270,28,rx=7,ry=7,fillColor=colors.HexColor('#e8eff6'),strokeColor=colors.HexColor('#2b5875')))
        d.add(String(255,y+10,name.replace('_',' ').strip() or name,textAnchor='middle',fontSize=9))
        if i:
            d.add(Line(255,y+38,255,y+29,strokeColor=colors.HexColor('#2b5875')))
            d.add(Polygon([252,y+32,258,y+32,255,y+28],fillColor=colors.HexColor('#2b5875')))
    return d


def render(text,summaries,changes,worst,alerts,fine):
    reports=ROOT/'reports';styles=getSampleStyleSheet()
    for name in ('Title','Heading2','Heading3'):styles[name].keepWithNext=True
    styles.add(ParagraphStyle(name='SmallTable',fontName='Helvetica',fontSize=8,leading=11))
    styles.add(ParagraphStyle(name='MonoWrap',fontName='Courier',fontSize=7,leading=9))
    story=[]
    def para(value,style='BodyText'):
        story.append(Paragraph(escape(str(value)).replace('\n','<br/>'),styles[style]))
        if not style.startswith('Heading') and style!='Title':story.append(Spacer(1,6))
    def heading(value):para(value,'Heading2')
    def table(headers,rows,widths=None):
        header_style=ParagraphStyle('TableHeader',parent=styles['SmallTable'],textColor=colors.white,fontName='Helvetica-Bold')
        data=[[Paragraph(escape(str(x)),header_style) for x in headers]]+[[Paragraph(escape('—' if x is None else str(x)),styles['SmallTable']) for x in row] for row in rows]
        t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#18354a')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#ccd5dc')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f0f4f7')]),('BOTTOMPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6)]))
        story.append(t);story.append(Spacer(1,10))
    def pct(value):return 'N/A' if value is None else f'{100*value:.1f}%'
    para('Taller 04 · Incident Commander','Title')
    para('Evaluación, observabilidad y protección · Opción C','Heading2')
    para('Mediciones del 14 de octubre de 2026. Kubernetes y alertas simulados; modelos H200, embeddings, Qdrant y Langfuse reales.')
    table(['Componente','Configuración'],[['Agentes','zai-org/GLM-5.3-Flash · vLLM :12555'],['Juez','gpt-oss:120b · Ollama :11434 · think=low · contexto 16384 · temperatura 0'],['RAG','bge-m3:latest · taller04_kubernetes · runbooks y snapshot atribuido'],['Observabilidad','Langfuse 4.50.0 local · SDK 4.17.0'],['Diseño experimental','Mismo golden, modelos, prompt SRE y verificador; cambia guardrail v1/v2']],[105,405])
    heading('Grafo de agentes')
    d=graph_drawing(reports/'grafo_agentes.mmd')
    story.append(d)
    from reportlab.graphics import renderSVG
    renderSVG.drawToFile(d,str(reports/'grafo_agentes.svg'))
    para('El guardrail de entrada envuelve el grafo: un bloqueo termina antes de llamar al modelo. Cada nodo tiene un span agent; la consulta RAG es retriever. La aprobación para reinicios se proporciona fuera del texto del usuario y solo afecta al simulador.')
    story.append(PageBreak())
    heading('Parte 0 · errores reproducidos')
    for key in ['ceros','guardrails','traza']:
        para(key,'Heading3')
        raw=(reports/f'parte0_{key}.txt').read_text()
        # Keep the complete exercise output; remove only font-cache diagnostics.
        raw=raw.split('/Users/AndyEdu/.matplotlib')[0].strip()
        for line in raw.splitlines():para(line,'MonoWrap')
    para('Un reporte en ceros hace pasar ausencia de datos por mal desempeño; un error revela el problema. No aplica se excluye del denominador; fallo cuenta como cero. A02/A03 expresan la misma intención pese a la tilde. L01 y L03 alteran números y fechas legítimos: L03 termina consultando un rango distinto. En instrumented_agent.py, línea 47 conserva el texto bloqueado; línea 45 empieza después del guardrail de línea 44; línea 58 escribe después de agent.run de línea 50, sin finally. Se corrigen con máscara recursiva, raíz que incluye guardrails y cierre ante errores.')
    heading('Parte 1 · observabilidad exportada de Langfuse')
    table(['Versión','Corridas','Entrada','Salida','Costo H200','Pago hipotético','p50 / p95 (s)'],[[v,s['corridas'],s['tokens_entrada'],s['tokens_salida'],'$0',f"${s['costo_hipotetico_usd']:.5f}",f"{s['p50_ms']/1000:.2f} / {s['p95_ms']/1000:.2f}"] for v,s in summaries.items()],[40,42,65,65,60,100,138])
    para('Pago hipotético: fila propietario_economico del anexo, USD 0.15 entrada y 0.60 salida por millón, fecha de verificación 2026-08-26. Es el precio del enunciado, no una tarifa actual. Los tokens de salida ya incluyen razonamiento del proveedor; no se cuentan dos veces.')
    for v,s in summaries.items():
        para(v+' · tiempo por tipo de span','Heading3')
        table(['Tipo','Tiempo acumulado (s)'],[[k,f'{t/1000:.3f}'] for k,t in s['tiempo_por_tipo_ms'].items()],[200,310])
        table(['Agente','Tiempo total (s)','Tokens bajo ese agente'],[[a,f"{m['duracion_ms']/1000:.3f}",m['tokens']] for a,m in s['agentes'].items()],[250,120,140])
        roles={a:m for a,m in s['agentes'].items() if m['duracion_ms']>0}
        bottleneck=max(roles,key=lambda a:roles[a]['duracion_ms'])
        most_tokens=max(s['agentes'],key=lambda a:s['agentes'][a]['tokens'])
        para(f"Mayor consumo de tokens: {most_tokens}, con {s['agentes'][most_tokens]['tokens']} tokens de entrada y salida acumulados.")
        para(f'Cuello de botella por suma de tiempo de agentes: {bottleneck}. Padres e hijos se solapan: estas duraciones no deben sumarse para calcular tiempo de pared.')
        para('Cotejo exportación/testigo: '+(reports/v/'export_verificacion.json').read_text())
    para('Se preservó una corrida fallida por presupuesto insuficiente: error_spans_exportados.jsonl contiene sus spans de error exportados. La raíz incluye guardrails y se cierra aunque falle. La máscara recorre dict, list y tuple. La base v1 tuvo pérdidas durante recuperación de PostgreSQL y errores de memoria de ClickHouse; se recuperaron desde las mediciones originales, con mismos IDs/tokens/respuestas, procedencia explícita y tiempo inicial derivado del fin menos duración. La entrega se consultó y exportó después del servidor. infra/ explica la corrección reversible y las limitaciones de tiempos recuperados.')
    heading('Parte 2 · golden set y resultados')
    cases=json.loads((ROOT/'golden_set.json').read_text())
    table(['ID','Tipo','Pregunta (PII redactada)','Comprobación'],[[c['id'],c['tipo'],mask(c['pregunta']),json.dumps(c.get('kubectl_verificacion') or c.get('criterio_juez') or c.get('respuesta_esperada'),ensure_ascii=False)] for c in cases],[35,55,190,230])
    para('Diez casos llevan verificación kubectl y respuesta_esperada, dos son ambiguos, dos negativos, tres adversariales, dos respondibles incluyen pii y uno comprueba reinicio sin aprobación. El snapshot de verificación es independiente del LLM. El número principal se compara contra la verdad derivada del snapshot; los identificadores P1, P2 y P3 no son cantidades. En negativas/adversariales se exige frase exacta y ausencia de cambios o herramientas prohibidas.')
    for v,s in summaries.items():
        para(v,'Heading3')
        table(['Tipo','N','Automático','Juez','Abstención','PII filtrada'],[[m['tipo'],m['n'],pct(m['automatico']),pct(m['juez']),pct(m['abstencion']),m['pii_filtrada']] for m in s['por_tipo']],[90,35,100,100,100,85])
        cal=json.loads((reports/v/'calibracion.json').read_text())
        table(['Comparación','N','Acuerdo','Kappa'],[[name,m['n'],pct(m['acuerdo']),m['kappa']] for name,m in cal.items() if name in ('automatico','humano')],[200,50,130,130])
    para('El usuario etiquetó diez respuestas como aprueba, incluidas las dos ambiguas, antes del juez. Se preservan sus decisiones sin corregirlas para aumentar el acuerdo. Una sola clase humana no permite estimar su discriminación entre aprueba/falla; kappa puede ser degenerado o cero según el otro evaluador. La calibración previa usa controles sintéticos balanceados y no sustituye estas etiquetas.')
    pre=json.loads((reports/'judge_preflight.json').read_text());para('Controles previos del juez: '+json.dumps(pre['metricas'],ensure_ascii=False))
    analysis=json.loads((reports/'analisis_desacuerdos.json').read_text())
    para('Desacuerdos revisados','Heading3')
    for item in analysis['desacuerdos_revisados']:
        para(f"{item['id']} · comparación con {item['contra']} · etiqueta {item['etiqueta']}, juez {item['juez']}",'Heading3')
        para(item['revision'])
        para('Conclusión: '+item['conclusion']+'. Traza: '+item['traza_id'])
    para(analysis['limite_etiquetas_humanas'])
    para(analysis['limite_controles_previos'])
    para(analysis['revision_mejorada'])
    heading('RAGAS')
    means=[]
    for v in ['v1','v2']:
        rows=list(csv.DictReader((reports/v/'ragas_resultados.csv').open()))
        for metric in sorted({x['metrica'] for x in rows}):
            values=[float(x['valor']) for x in rows if x['metrica']==metric and x['valor']!='' and not x['error']]
            means.append([v,metric,len(values),f'{statistics.mean(values):.4f}'])
    table(['Versión','Métrica','N','Media'],means,[60,240,60,150])
    para('La caché se identifica por hash de todas las entradas relevantes, esquema y configuración del juez. Solo se reutilizan juicios reales de entradas idénticas; cache_source conserva la procedencia y las lecturas de caché no se contabilizan como tokens nuevos. Precisión y recall pueden compartir resultados entre v1/v2 porque sus entradas no incluyen la respuesta generada. La relevancia mantiene tres iteraciones a temperatura cero; las solicitudes idénticas pueden compartir juicio, por lo que no son tres muestras independientes.')
    para('La precisión de contexto de C19 en v1 sufrió un timeout. Tras terminar las ejecuciones se recuperó desde la caché de v2 con el mismo hash de entrada, sin nuevas inferencias ni sustitución por cero. El error original y la resolución se conservan en v1/ragas_errores_reintentos.jsonl.')
    para('RAGAS 0.4.3 usa sus prompts y fórmulas oficiales con gpt-oss:120b. Fidelidad pregunta qué afirmaciones de la respuesta están respaldadas; precisión y recall comparan contextos con la referencia. Relevancia usa embeddings bge-m3. No se aplica a negativas, adversariales ni ambiguas. La correlación con exactitud no se presupone.')
    proof=json.loads((reports/'ragas_verificacion.json').read_text())
    para('Contraste con ragas.ascore · '+proof['version']+' '+proof['id'],'Heading3')
    table(['Métrica','Implementación docente','ragas.ascore','Coincide'],[[name,f"{m['docente']:.6f}",f"{m['ragas_ascore']:.6f}",m['coincide']] for name,m in proof['metricas'].items()],[170,130,130,80])
    contradiction=json.loads((reports/'contradiccion_ragas.json').read_text())
    para(contradiction['id']+' · exactitud y fidelidad','Heading3')
    para(contradiction['interpretacion'])
    para(contradiction['revision_manual'])
    if extra:=contradiction.get('revision_adicional'):
        para(f"{extra['id']} · exactitud {extra['automatico']}, fidelidad {extra['fidelidad']}",'Heading3')
        para(extra['revision_manual'])
    para('Los juicios NLI completos y su evidencia se conservan en contradiccion_ragas.json.')
    heading('Tres peores casos y mejora medida')
    for item in json.loads((reports/'analisis_peores.json').read_text()):
        para(item['id']+' · '+item['categoria'],'Heading3')
        para(item['evidencia'])
        para('Cambio: '+item['mejora'])
        para(f"Tokens: {item['tokens_base']} → {item['tokens_mejorada']}. Estado: {item['status_base']} → {item['status_mejorada']}.")
        para('Trazas base / mejorada: '+item['traza_base']+' / '+item['traza_mejorada'])
        if item.get('revision_juez'):para(item['revision_juez'])
    para('Los spans completos están en peores_casos.json; contienen los prompts, outputs del modelo, decisión del guardrail y respuesta final. v2 mejora intención normalizada de inyección y canonicaliza una abstención que el propio modelo ya emitió. El prompt LLM se mantiene: su versión Langfuse está ligada a la generación. prompt_version v1/v2 identifica la implementación del guardrail; CHANGELOG.md documenta el significado.')
    table(['ID','Auto base','Auto v2','Juez base','Juez v2','Tokens base','Tokens v2','Intervención'],[[c['id'],c['base'],c['mejorada'],c['juez_base'],c['juez_mejorada'],c['tokens_base'],c['tokens_mejorada'],c['intervencion']] for c in changes],[35,40,40,40,40,80,80,155])
    para('Los cambios buscados se comprueban en decisiones de guardrail y llamadas evitadas, no solo en scores. Los cambios ajenos a esos casos pueden deberse a ejecución del modelo aun con temperatura cero. Con veinte casos la resolución es 5%; no se afirman diferencias pequeñas con confianza estadística.')
    heading('Parte 3 · guardrails como clasificadores')
    results=json.loads((reports/'guardrails_resumen.json').read_text())
    table(['Implementación','Casos','Correctos','FN','FP','Tasa FN','Tasa FP'],[[k,v['casos'],v.get('correcto',0),v.get('falso_negativo',0),v.get('falso_positivo',0),pct(v.get('tasa_falsos_negativos')),pct(v.get('tasa_falsos_positivos'))] for k,v in results.items()],[100,45,65,45,45,105,105])
    para('Mismo banco: 17 casos docentes más dos ataques y dos preguntas legítimas Kubernetes. Se usan intención normalizada y redacción contextual; no NER, por lo que nombres de personas y formatos no previstos pueden escapar. El reinicio exige aprobación booleana externa y payments/checkout-api en allowlist. Secretos con forma reconocible se bloquean, hashes y UUID se conservan. Un banco perfecto no demuestra seguridad fuera de él.')
    new_rows=list(csv.DictReader((reports/'v2/resultados.csv').open()));spans=[json.loads(l) for l in (reports/'v2/spans.jsonl').read_text().splitlines()]
    demo=[]
    for case,name in [('C16','input'),('C18','input'),('C20','restart.allowlist')]:
        row=next(r for r in new_rows if r['id']==case)
        span=next(s for s in spans if s['traza']==row['traza_id'] and s['nombre']==name and s['span']=='guardrail')
        demo.append([case,name,span.get('output'),f"{span['duracion_ms']:.3f}",row['traza_id']])
    table(['Caso','Guarda','Decisión','ms','Traza'],demo,[35,90,150,55,180])
    guard=[s['duracion_ms'] for s in spans if s['span']=='guardrail']
    para(f'Guardrails sin LLM: costo monetario directo cero; mediana observada {statistics.median(guard):.3f} ms. Los CSV individuales permiten revisar cada falso positivo y falso negativo.')
    heading('Parte 4 · ¿ajuste fino?')
    para(fine)
    heading('Monitoreo')
    table(['Alerta','Umbral medido','Ventana','Primera inspección'],[[a['nombre'],f"{a['umbral']:.3f} {a['unidad']}",a['ventana'],a['mirar']] for a in alerts],[60,120,150,180])
    para('Umbrales derivados de v2 y por encima de la resolución del golden. Las tasas del banco adversarial no representan tráfico de producción; los límites se recalibran con tráfico real y ventana mínima de veinte corridas.')
    heading('Reproducibilidad y límites')
    para('Fuentes: resultados.csv v1/v2, spans.jsonl exportados y cotejados, ragas_resultados.csv, guardrails_propios/ejemplo.csv, etiquetas.csv, calibraciones y manifest.json. Los entornos y modelos están fijados; .env queda fuera de Git. No se publican credenciales. El simulador nunca llama shell ni un cluster real. La revisión humana solo contiene etiquetas positivas: es una limitación explícita, no prueba de ausencia de errores.')
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#526879'));canvas.drawString(42,25,'Taller04 · opción C · resultados reales sobre Kubernetes simulado');canvas.drawRightString(A4[0]-42,25,str(doc.page));canvas.restoreState()
    SimpleDocTemplate(str(reports/'informe_taller04.pdf'),pagesize=A4,leftMargin=42,rightMargin=42,topMargin=40,bottomMargin=40).build(story,onFirstPage=footer,onLaterPages=footer)
