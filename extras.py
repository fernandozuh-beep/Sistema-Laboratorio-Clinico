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
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
    M = _M(); o = M.get_o(db, id)
    if not o.resultados: raise HTTPException(422, "La orden aún no tiene resultados")
    val = db.query(m.Auditoria).filter(m.Auditoria.folio == o.folio, m.Auditoria.accion == "Estado → Entregado").first()
    S, p = getSampleStyleSheet(), o.paciente
    el = [Paragraph(f"<b>{HOSPITAL}</b> · Laboratorio clínico", S["Title"]),
          Paragraph(f"<b>Paciente:</b> {p.nombre} &nbsp; <b>Expediente:</b> {p.expediente} &nbsp; <b>Sexo:</b> {p.sexo} &nbsp; <b>Nac.:</b> {p.fecha_nac or '—'}", S["Normal"]),
          Paragraph(f"<b>Folio:</b> {o.folio} &nbsp; <b>Estudio:</b> {o.tipo_analisis} &nbsp; <b>Solicitante:</b> {o.solicitante or '—'}", S["Normal"])]
    if o.estado != "Entregado":
        el.append(Paragraph("<font color='#c62828'><b>RESULTADO PRELIMINAR — NO VALIDADO</b></font>", S["Normal"]))
    rows, sty = [["Parámetro", "Resultado", "Unidad", "Referencia", "Interpretación"]], [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10302f")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), .4, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9)]
    for k, x in logic.evaluar(o.tipo_analisis, o.resultados).items():
        if x["valor"] is None: continue
        rows.append([k, x["valor"], x["u"], f"{x['min']} – {x['max']}", x["flag"].upper()])
        if x["flag"] != "normal":
            sty.append(("TEXTCOLOR", (0, len(rows) - 1), (-1, len(rows) - 1), colors.HexColor("#c62828" if x["flag"] == "crítico" else "#b26a00")))
    el += [Spacer(1, 14), Table(rows, style=TableStyle(sty), hAlign="LEFT")]
    if o.observaciones: el.append(Paragraph(f"<br/><b>Observaciones:</b> {o.observaciones}", S["Normal"]))
    el.append(Paragraph(f"<br/><br/>Validó: {val.usuario if val else '________________'} &nbsp;·&nbsp; Impreso: {datetime.now():%d/%m/%Y %H:%M} por {u['sub']}", S["Normal"]))
    M.audit(db, u["sub"], "Reporte PDF generado", o.folio); db.commit()
    buf = io.BytesIO(); SimpleDocTemplate(buf, pagesize=letter).build(el); buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename={o.folio}.pdf"})

# ---------- Gestión de usuarios (solo admin) ----------
class UserIn(BaseModel):
    username: str = Field(pattern="^[a-z0-9._-]{3,50}$")
    nombre: str = Field(min_length=3, max_length=100)
    rol: str = Field(pattern="^(admin|medico|quimico|recepcion)$")
    password: str | None = Field(None, min_length=8)
    activo: bool = True

@router.get("/api/usuarios")
def usuarios(db=Depends(get_db), u=Depends(sec.roles("admin"))):
    return [{"id": x.id, "username": x.username, "nombre": x.nombre, "rol": x.rol, "activo": x.activo}
            for x in db.query(m.Usuario).order_by(m.Usuario.id)]

@router.post("/api/usuarios", status_code=201)
def crear_usuario(d: UserIn, db=Depends(get_db), u=Depends(sec.roles("admin"))):
    if not d.password: raise HTTPException(422, "La contraseña es obligatoria (mínimo 8 caracteres)")
    if db.query(m.Usuario).filter_by(username=d.username).first(): raise HTTPException(409, "Ese usuario ya existe")
    db.add(m.Usuario(username=d.username, nombre=d.nombre, rol=d.rol, activo=d.activo, hashed_password=sec.hash_pw(d.password)))
    _M().audit(db, u["sub"], f"Usuario creado: {d.username} ({d.rol})"); db.commit()
    return {"ok": True}

@router.put("/api/usuarios/{id}")
def editar_usuario(id: int, d: UserIn, db=Depends(get_db), u=Depends(sec.roles("admin"))):
    x = db.get(m.Usuario, id)
    if not x: raise HTTPException(404, "Usuario no encontrado")
    if x.username == u["sub"] and (not d.activo or d.rol != "admin"):
        raise HTTPException(422, "No puedes desactivarte ni quitarte el rol admin a ti mismo")
    x.nombre, x.rol, x.activo, x.intentos, x.bloqueado_hasta = d.nombre, d.rol, d.activo, 0, None
    if d.password: x.hashed_password = sec.hash_pw(d.password)
    _M().audit(db, u["sub"], f"Usuario editado: {x.username} ({d.rol}, {'activo' if d.activo else 'inactivo'})"); db.commit()
    return {"ok": True}
