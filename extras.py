import io, os, re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import StreamingResponse, PlainTextResponse
from pydantic import BaseModel, Field
import models as m, security as sec, logic
from models import get_db

router = APIRouter()
HOSPITAL = os.getenv("OCAC_HOSPITAL", "Hospital General")
ANALIZADOR_KEY = os.getenv("OCAC_ANALYZER_KEY", "analizador-demo-key")
DELTA_DEFAULT = 30  # % máximo de cambio aceptado entre dos resultados consecutivos del mismo paciente
DELTA = {"Hemoglobina": 20, "Potasio": 20, "Sodio": 5, "Creatinina": 50, "Plaquetas": 50}
LOINC = {"Hemoglobina": "718-7", "Leucocitos": "6690-2", "Plaquetas": "777-3", "Glucosa": "2345-7",
         "Creatinina": "2160-0", "Urea": "3094-0", "Colesterol total": "2093-3", "Triglicéridos": "2571-8",
         "HDL": "2085-9", "Sodio": "2951-2", "Potasio": "2823-3", "Cloro": "2075-0", "Troponina I": "10839-9",
         "INR": "6301-6", "TP": "5902-2", "TTPa": "3173-2", "HbA1c": "4548-4"}

def _M():
    import main; return main

# ---------- Delta-check ----------
def previos(db, o):
    q = db.query(m.Orden).filter(m.Orden.paciente_id == o.paciente_id, m.Orden.id != o.id,
                                 m.Orden.eliminado == False).order_by(m.Orden.creado).all()
    return [x for x in q if x.resultados]

def delta(db, o):
    res, ant = {}, previos(db, o)
    for k, v in (o.resultados or {}).items():
        h = [(x.creado, x.resultados[k]) for x in ant if k in x.resultados and x.creado < o.creado]
        if not h or not h[-1][1]: continue
        f, p = h[-1]
        pct = round((v - p) / p * 100, 1)
        if abs(pct) > DELTA.get(k, DELTA_DEFAULT):
            res[k] = {"previo": p, "actual": v, "pct": pct, "fecha": f.isoformat()}
    return res

async def guardar(db, o, valores, usuario):
    """Captura de resultados (usada por el químico y por los analizadores)."""
    M = _M()
    if o.estado == "Entregado": raise HTTPException(409, "Una orden entregada ya no se puede modificar")
    malos = [k for k in valores if k not in logic.CATALOGO[o.tipo_analisis]["params"]]
    if malos: raise HTTPException(422, f"Parámetros no válidos: {', '.join(malos)}")
    prev, o.resultados = o.resultados, valores
    if o.estado == "Recepcionado": o.estado = "Procesando"
    crit = logic.hay_critico(o.tipo_analisis, valores)
    if crit: o.prioridad = 1
    M.audit(db, usuario, "Resultados capturados", o.folio, prev, valores)
    db.commit(); db.refresh(o)
    dl = delta(db, o)
    base = {"folio": o.folio, "paciente": o.paciente.nombre}
    if crit: await M.hub.alert({**base, "nivel": "critico", "mensaje": f"Valor crítico en {o.tipo_analisis}"})
    if dl: await M.hub.alert({**base, "nivel": "delta", "mensaje": "Delta-check: cambio brusco en " + ", ".join(dl)})
    return o

@router.get("/api/ordenes/{id}/historial")
def historial(id: int, db=Depends(get_db), u=Depends(sec.user)):
    o = _M().get_o(db, id)
    series = {k: [] for k in logic.CATALOGO[o.tipo_analisis]["params"]}
    for x in sorted(previos(db, o) + [o], key=lambda x: x.creado):
        for k, v in (x.resultados or {}).items():
            if k in series: series[k].append({"fecha": x.creado.isoformat(), "valor": v, "folio": x.folio})
    return {"series": {k: s for k, s in series.items() if s}, "delta": delta(db, o)}

# ---------- Analizadores: HL7 v2 (ORU^R01) ----------
@router.post("/api/analizador/hl7")
async def hl7(req: Request, x_api_key: str = Header(""), db=Depends(get_db)):
    if x_api_key != ANALIZADOR_KEY: raise HTTPException(401, "Clave de analizador inválida")
    txt = (await req.body()).decode("utf-8", "ignore")
    ack = lambda c, t: PlainTextResponse(f"MSH|^~\\&|OCAC|{HOSPITAL}|||{datetime.now():%Y%m%d%H%M%S}||ACK|1|P|2.5\rMSA|{c}|{t}\r")
    try:
        folio, obx = "", []
        for s in re.split(r"[\r\n]+", txt.strip()):
            f = s.split("|")
            if f[0] == "OBR" and len(f) > 3: folio = (f[3] or f[2]).split("^")[0]
            if f[0] == "OBX" and len(f) > 5 and f[2] == "NM": obx.append((f[3].split("^"), float(f[5])))
        o = db.query(m.Orden).filter_by(folio=folio, eliminado=False).first()
        if not o: return ack("AE", f"Folio {folio} no encontrado")
        inv, params, vals = {v: k for k, v in LOINC.items()}, logic.CATALOGO[o.tipo_analisis]["params"], {}
        for c, val in obx:
            nom = inv.get(c[0]) or next((p for p in params if p.casefold() == (c[1] if len(c) > 1 else c[0]).casefold()), None)
            if nom in params: vals[nom] = val
        if not vals: return ack("AE", "Sin resultados reconocidos para este análisis")
        await guardar(db, o, {**(o.resultados or {}), **vals}, "analizador")
        return ack("AA", "Resultados recibidos")
    except HTTPException as e: return ack("AE", str(e.detail))
    except Exception: return ack("AE", "Mensaje HL7 mal formado")

# ---------- Exportación FHIR R4 ----------
@router.get("/api/ordenes/{id}/fhir")
def fhir(id: int, db=Depends(get_db), u=Depends(sec.user)):
    o = _M().get_o(db, id)
    if not o.resultados: raise HTTPException(422, "La orden aún no tiene resultados")
    pid, st = f"Patient/{o.paciente.expediente}", ("final" if o.estado == "Entregado" else "preliminary")
    IC = lambda c: {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "code": c}]}
    obs = []
    for k, p in logic.evaluar(o.tipo_analisis, o.resultados).items():
        if p["valor"] is None: continue
        code = {"normal": "N", "alto": "H", "bajo": "L"}.get(p["flag"]) or ("LL" if p["valor"] < p["min"] else "HH")
        obs.append({"resourceType": "Observation", "id": f"{o.folio}-{k}".replace(" ", "_"), "status": st,
            "code": {"coding": [{"system": "http://loinc.org", "code": LOINC.get(k, ""), "display": k}], "text": k},
            "subject": {"reference": pid}, "valueQuantity": {"value": p["valor"], "unit": p["u"]},
            "interpretation": [IC(code)], "referenceRange": [{"low": {"value": p["min"]}, "high": {"value": p["max"]}}]})
    rep = {"resourceType": "DiagnosticReport", "id": o.folio, "status": st,
           "code": {"text": o.tipo_analisis}, "subject": {"reference": pid},
           "issued": o.actualizado.isoformat(), "result": [{"reference": "Observation/" + x["id"]} for x in obs]}
    pac = {"resourceType": "Patient", "id": o.paciente.expediente, "name": [{"text": o.paciente.nombre}],
           "gender": "male" if o.paciente.sexo == "M" else "female", "birthDate": o.paciente.fecha_nac}
    return {"resourceType": "Bundle", "type": "collection",
            "entry": [{"resource": r} for r in [pac, *obs, rep]]}

# ---------- Reporte PDF ----------
@router.get("/api/ordenes/{id}/pdf")
def pdf(id: int, db=Depends(get_db), u=Depends(sec.user)):
    from xml.sax.saxutils import escape as xesc
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                    Table, TableStyle, Spacer, Image)
    M = _M(); o = M.get_o(db, id)
    if not o.resultados: raise HTTPException(422, "La orden aún no tiene resultados")
    val = db.query(m.Auditoria).filter(m.Auditoria.folio == o.folio, m.Auditoria.accion == "Estado → Entregado").first()
    p = o.paciente
    INDIGO, TEAL = colors.HexColor("#4f46e5"), colors.HexColor("#0e7c86")
    GRIS, BORDE = colors.HexColor("#64748b"), colors.HexColor("#d7dee9")
    W = letter[0] - 72  # 540 pt útiles: márgenes de 36 pt por lado

    def fmt_dt(dt):
        return dt.strftime("%d/%m/%Y %H:%M") if dt else "—"
    def edad_de(fn):
        try: n = datetime.strptime(fn or "", "%Y-%m-%d").date()
        except Exception: return None
        h = datetime.now().date(); a = h.year - n.year - ((h.month, h.day) < (n.month, n.day))
        return a if a >= 0 else None
    def fnac(fn):
        try: return datetime.strptime(fn or "", "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception: return fn or "—"

    st_title = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=22, leading=24, textColor=INDIGO)
    st_sub = ParagraphStyle("subtitulo", fontName="Helvetica", fontSize=8, leading=10, textColor=GRIS)
    st_hosp = ParagraphStyle("hosp", fontName="Helvetica-Bold", fontSize=11.5, leading=14, alignment=TA_RIGHT)
    st_hosp2 = ParagraphStyle("hosp2", fontName="Helvetica", fontSize=9, leading=12, textColor=GRIS, alignment=TA_RIGHT)
    st_est = ParagraphStyle("estudio", fontName="Helvetica-Bold", fontSize=10.5, leading=13, alignment=TA_RIGHT)
    st_cell = ParagraphStyle("celda", fontName="Helvetica", fontSize=9.5, leading=12.5)
    st_th = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=colors.white)
    st_td = ParagraphStyle("td", fontName="Helvetica", fontSize=9.5, leading=12.5)
    st_tdc = ParagraphStyle("tdc", parent=st_td, alignment=TA_CENTER)
    st_tdb = ParagraphStyle("tdb", parent=st_td, fontName="Helvetica-Bold", alignment=TA_CENTER)
    st_prel = ParagraphStyle("prel", fontName="Helvetica-Bold", fontSize=10.5, leading=13,
                             textColor=colors.HexColor("#c62828"), alignment=TA_CENTER)
    st_obs = ParagraphStyle("obs", fontName="Helvetica", fontSize=9.5, leading=13)
    st_firma = ParagraphStyle("firma", fontName="Helvetica", fontSize=9.5, leading=12)

    def celda(*pares):
        return Paragraph("<br/>".join(
            f"<font size=7.5 color='#64748b'><b>{t}</b></font><br/><font size=10>{xesc(str(v))}</font>"
            for t, v in pares), st_cell)

    # --- Encabezado: logo + marca + hospital/estudio ---
    logo = ""
    try:
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "logo.png")
        if os.path.isfile(ruta): logo = Image(ruta, width=52, height=52, kind="proportional")
    except Exception:
        logo = ""
    el = [Table([[logo,
                  [Paragraph("MonOCAC", st_title), Paragraph("SISTEMA DE MONITOREO Y ANÁLISIS CLÍNICO", st_sub)],
                  [Paragraph(xesc(HOSPITAL), st_hosp), Paragraph("Laboratorio clínico", st_hosp2),
                   Paragraph(xesc(o.tipo_analisis), st_est)]]],
                colWidths=[60, 290, 190], style=TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (0, 0), 0), ("LEFTPADDING", (2, 0), (2, 0), 6),
                    ("RIGHTPADDING", (2, 0), (2, 0), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)])),
          Table([["", ""]], colWidths=[W / 2, W / 2], rowHeights=[4], style=TableStyle([
              ("BACKGROUND", (0, 0), (0, 0), TEAL), ("BACKGROUND", (1, 0), (1, 0), INDIGO),
              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
              ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)])),
          Spacer(1, 12)]

    # --- Tarjeta del paciente ---
    ed = edad_de(p.fecha_nac)
    prio = {1: "Crítica", 2: "Urgente", 3: "Rutina"}.get(o.prioridad, "—")
    sexo = {"M": "Masculino", "F": "Femenino"}.get(p.sexo, p.sexo or "—")
    area = logic.CATALOGO.get(o.tipo_analisis, {}).get("area")
    tarjeta = Table([
        [celda(("PACIENTE", p.nombre), ("EXPEDIENTE", p.expediente)),
         celda(("EDAD", f"{ed} años" if ed is not None else "—"), ("SEXO", sexo), ("FECHA DE NACIMIENTO", fnac(p.fecha_nac))),
         celda(("FOLIO", o.folio), ("PRIORIDAD", prio), ("ESTADO", o.estado))],
        [celda(("ESTUDIO", o.tipo_analisis + (f" · {area}" if area else ""))),
         celda(("SOLICITANTE", o.solicitante or "—")),
         celda(("RECIBIDO", fmt_dt(o.creado)), ("ACTUALIZADO", fmt_dt(o.actualizado)))]],
        colWidths=[190, 175, 175], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef2ff")),
            ("BOX", (0, 0), (-1, -1), .6, BORDE), ("INNERGRID", (0, 0), (-1, -1), .4, BORDE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    el.append(tarjeta)

    # --- Aviso de resultado preliminar ---
    if o.estado != "Entregado":
        el += [Spacer(1, 10), Table([[Paragraph("RESULTADO PRELIMINAR — NO VALIDADO", st_prel)]],
               colWidths=[W], style=TableStyle([
                   ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fdecec")),
                   ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))]
    el.append(Spacer(1, 12))

    # --- Tabla de resultados a todo lo ancho ---
    FCOLOR = {"crítico": "#c62828", "alto": "#b26a00", "bajo": "#b26a00", "normal": "#3f7a52"}
    rows = [[Paragraph(h, st_th) for h in ["Parámetro", "Resultado", "Unidad", "Referencia", "Interpretación"]]]
    sty = [("BACKGROUND", (0, 0), (-1, 0), INDIGO),
           ("GRID", (0, 0), (-1, -1), .4, BORDE),
           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
           ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    for k, x in logic.evaluar(o.tipo_analisis, o.resultados).items():
        if x["valor"] is None: continue
        i = len(rows)
        if x["flag"] == "crítico":
            sty.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fdf0f0")))
        elif i % 2 == 0:
            sty.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f6f8fc")))
        rows.append([Paragraph(xesc(k), st_td),
                     Paragraph(f"<b>{x['valor']}</b>", st_tdb),
                     Paragraph(xesc(str(x["u"])), st_tdc),
                     Paragraph(f"{x['min']} – {x['max']}", st_tdc),
                     Paragraph(f"<font color='{FCOLOR.get(x['flag'], '#64748b')}'><b>{x['flag'].upper()}</b></font>", st_tdc)])
    el.append(Table(rows, colWidths=[196, 92, 66, 102, 84], style=TableStyle(sty), repeatRows=1))

    # --- Observaciones ---
    if o.observaciones:
        el += [Spacer(1, 12), Table([[Paragraph(f"<b>Observaciones:</b> {xesc(o.observaciones)}", st_obs)]],
               colWidths=[W], style=TableStyle([
                   ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
                   ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                   ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))]

    # --- Firma (el «Impreso…» vive en el pie de página) ---
    el += [Spacer(1, 30), Table([[""], [Paragraph(f"Validó: <b>{xesc(val.usuario)}</b>" if val else "Validó: ________________", st_firma)]],
           colWidths=[200], rowHeights=[26, 14], hAlign="LEFT", style=TableStyle([
               ("LINEBELOW", (0, 0), (-1, 0), .7, colors.HexColor("#1e2433")),
               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))]

    # --- Documento con pie en cada página ---
    def pie(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(BORDE); canvas.setLineWidth(.4)
        canvas.line(36, 36, letter[0] - 36, 36)
        canvas.setFont("Helvetica", 7.5); canvas.setFillColor(GRIS)
        canvas.drawString(36, 26, f"MonOCAC · {HOSPITAL}")
        canvas.drawCentredString(letter[0] / 2, 26, o.folio)
        canvas.drawRightString(letter[0] - 36, 26, f"Impreso {datetime.now():%d/%m/%Y %H:%M} por {u['sub']} · Página {doc.page}")
        canvas.restoreState()
    M.audit(db, u["sub"], "Reporte PDF generado", o.folio); db.commit()
    buf = io.BytesIO()
    doc_tpl = BaseDocTemplate(buf, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=48,
                              title=f"MonOCAC {o.folio}", author="MonOCAC")
    frame = Frame(36, 48, W, letter[1] - 84, id="main", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc_tpl.addPageTemplates([PageTemplate(id="todo", frames=[frame], onPage=pie)])
    doc_tpl.build(el); buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename={o.folio}.pdf"})

# ---------- Gestión de usuarios (solo admin) ----------
class UserIn(BaseModel):
    username: str = Field(pattern="^[a-z0-9._-]{3,50}$")
    nombre: str = Field(min_length=3, max_length=100)
    rol: str = Field(pattern="^(admin|medico|quimico|recepcion)$")
    especialidad: str = ""
    password: str | None = Field(None, min_length=8)
    activo: bool = True

@router.get("/api/usuarios")
def usuarios(db=Depends(get_db), u=Depends(sec.roles("admin"))):
    return [{"id": x.id, "username": x.username, "nombre": x.nombre, "rol": x.rol,
             "especialidad": x.especialidad or "", "activo": x.activo}
            for x in db.query(m.Usuario).order_by(m.Usuario.id)]

@router.post("/api/usuarios", status_code=201)
def crear_usuario(d: UserIn, db=Depends(get_db), u=Depends(sec.roles("admin"))):
    if not d.password: raise HTTPException(422, "La contraseña es obligatoria (mínimo 8 caracteres)")
    if db.query(m.Usuario).filter_by(username=d.username).first(): raise HTTPException(409, "Ese usuario ya existe")
    db.add(m.Usuario(username=d.username, nombre=d.nombre, rol=d.rol, especialidad=d.especialidad, activo=d.activo, hashed_password=sec.hash_pw(d.password)))
    _M().audit(db, u["sub"], f"Usuario creado: {d.username} ({d.rol})"); db.commit()
    return {"ok": True}

@router.put("/api/usuarios/{id}")
def editar_usuario(id: int, d: UserIn, db=Depends(get_db), u=Depends(sec.roles("admin"))):
    x = db.get(m.Usuario, id)
    if not x: raise HTTPException(404, "Usuario no encontrado")
    if x.username == u["sub"] and (not d.activo or d.rol != "admin"):
        raise HTTPException(422, "No puedes desactivarte ni quitarte el rol admin a ti mismo")
    x.nombre, x.rol, x.activo, x.intentos, x.bloqueado_hasta = d.nombre, d.rol, d.activo, 0, None
    x.especialidad = d.especialidad
    if d.password: x.hashed_password = sec.hash_pw(d.password)
    _M().audit(db, u["sub"], f"Usuario editado: {x.username} ({d.rol}, {'activo' if d.activo else 'inactivo'})"); db.commit()
    return {"ok": True}
