import json, os, uuid
from datetime import timedelta
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import or_, func
import models as m, security as sec, logic
from models import get_db
import extras

m.Base.metadata.create_all(bind=m.engine)
app = FastAPI(title="OCAC - Hospital Intelligence System")

# ---------- Alertas en tiempo real (WebSocket autenticado) ----------
class Hub:
    def __init__(s): s.c = []
    async def connect(s, w): await w.accept(); s.c.append(w)
    def drop(s, w):
        if w in s.c: s.c.remove(w)
    async def alert(s, msg):
        for w in list(s.c):
            try: await w.send_text(json.dumps(msg))
            except Exception: s.drop(w)
hub = Hub()

@app.websocket("/ws/alertas")
async def ws(w: WebSocket, token: str = Query(...)):
    try: sec.decode(token)
    except HTTPException:
        await w.close(code=4401); return
    await hub.connect(w)
    try:
        while True: await w.receive_text()
    except WebSocketDisconnect:
        hub.drop(w)

# ---------- Esquemas ----------
class OrdenIn(BaseModel):
    expediente: str = Field(min_length=3, max_length=30)
    nombre: str = Field(min_length=3, max_length=120)
    sexo: str = Field("M", pattern="^[MF]$")
    fecha_nac: str | None = None
    tipo_analisis: str
    prioridad: int = Field(3, ge=1, le=3)
    solicitante: str = ""
    observaciones: str = ""
class EstadoIn(BaseModel): estado: str
class ResIn(BaseModel): resultados: dict[str, float]

# ---------- Utilidades ----------
def audit(db, user, accion, folio=None, prev=None, new=None):
    db.add(m.Auditoria(usuario=user, accion=accion, folio=folio, datos_previos=prev, datos_nuevos=new))

def out(o):
    return {"id": o.id, "folio": o.folio, "expediente": o.paciente.expediente, "paciente": o.paciente.nombre,
            "sexo": o.paciente.sexo, "fecha_nac": o.paciente.fecha_nac, "tipo_analisis": o.tipo_analisis,
            "area": logic.CATALOGO[o.tipo_analisis]["area"], "estado": o.estado, "prioridad": o.prioridad,
            "solicitante": o.solicitante, "observaciones": o.observaciones, "creado": o.creado.isoformat(),
            "analisis": logic.evaluar(o.tipo_analisis, o.resultados),
            "critico": logic.hay_critico(o.tipo_analisis, o.resultados)}

def get_o(db, id):
    o = db.get(m.Orden, id)
    if not o or o.eliminado: raise HTTPException(404, "Orden no encontrada")
    return o

# ---------- Autenticación ----------
@app.post("/api/auth/login")
def login(f: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    u = db.query(m.Usuario).filter_by(username=f.username).first()
    if u and u.bloqueado_hasta and u.bloqueado_hasta > m.now():
        raise HTTPException(429, "Cuenta bloqueada 10 minutos por intentos fallidos")
    if not u or not u.activo or not sec.check_pw(f.password, u.hashed_password):
        if u:
            u.intentos += 1
            if u.intentos >= 5: u.bloqueado_hasta, u.intentos = m.now() + timedelta(minutes=10), 0
            audit(db, u.username, "Login fallido"); db.commit()
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    u.intentos = 0; audit(db, u.username, "Login"); db.commit()
    return {"access_token": sec.make_token(u.username, u.rol), "token_type": "bearer",
            "usuario": u.username, "nombre": u.nombre, "rol": u.rol}

# ---------- Órdenes de análisis (CRUD) ----------
@app.get("/api/catalogo")
def catalogo(u=Depends(sec.user)): return logic.CATALOGO

@app.get("/api/ordenes")
def listar(q: str = "", estado: str = "", db=Depends(get_db), u=Depends(sec.user)):
    qs = db.query(m.Orden).join(m.Paciente).filter(m.Orden.eliminado == False)
    if estado: qs = qs.filter(m.Orden.estado == estado)
    if q:
        k = f"%{q}%"
        qs = qs.filter(or_(m.Orden.folio.ilike(k), m.Paciente.nombre.ilike(k),
                           m.Paciente.expediente.ilike(k), m.Orden.tipo_analisis.ilike(k)))
    return [out(o) for o in qs.order_by(m.Orden.prioridad, m.Orden.creado.desc()).limit(300)]

@app.post("/api/ordenes", status_code=201)
def crear(d: OrdenIn, db=Depends(get_db), u=Depends(sec.roles("admin", "medico", "recepcion"))):
    if d.tipo_analisis not in logic.CATALOGO: raise HTTPException(422, "El análisis no existe en el catálogo")
    p = db.query(m.Paciente).filter_by(expediente=d.expediente).first()
    if not p:
        p = m.Paciente(expediente=d.expediente, nombre=d.nombre, sexo=d.sexo, fecha_nac=d.fecha_nac)
        db.add(p); db.flush()
    o = m.Orden(folio=uuid.uuid4().hex[:12], paciente_id=p.id, tipo_analisis=d.tipo_analisis,
                prioridad=d.prioridad, solicitante=d.solicitante, observaciones=d.observaciones)
    db.add(o); db.flush()
    o.folio = f"OC-{m.now():%y%m%d}-{o.id:05d}"
    audit(db, u["sub"], "Orden creada", o.folio, None, {"analisis": d.tipo_analisis, "prioridad": d.prioridad})
    db.commit(); db.refresh(o)
    return out(o)

@app.put("/api/ordenes/{id}")
def editar(id: int, d: OrdenIn, db=Depends(get_db), u=Depends(sec.roles("admin", "medico", "recepcion"))):
    o = get_o(db, id)
    if o.estado == "Entregado": raise HTTPException(409, "Una orden entregada ya no se puede modificar")
    if d.tipo_analisis not in logic.CATALOGO: raise HTTPException(422, "El análisis no existe en el catálogo")
    prev = {"analisis": o.tipo_analisis, "prioridad": o.prioridad, "obs": o.observaciones}
    if d.tipo_analisis != o.tipo_analisis: o.resultados = None
    o.tipo_analisis, o.prioridad, o.solicitante, o.observaciones = d.tipo_analisis, d.prioridad, d.solicitante, d.observaciones
    o.paciente.nombre, o.paciente.sexo, o.paciente.fecha_nac = d.nombre, d.sexo, d.fecha_nac
    audit(db, u["sub"], "Orden editada", o.folio, prev,
          {"analisis": d.tipo_analisis, "prioridad": d.prioridad, "obs": d.observaciones})
    db.commit(); db.refresh(o)
    return out(o)

@app.delete("/api/ordenes/{id}")
def borrar(id: int, db=Depends(get_db), u=Depends(sec.roles("admin"))):
    o = get_o(db, id)
    o.eliminado = True
    audit(db, u["sub"], "Orden eliminada", o.folio, {"estado": o.estado}, None)
    db.commit()
    return {"ok": True}

@app.put("/api/ordenes/{id}/resultados")
async def capturar(id: int, d: ResIn, db=Depends(get_db), u=Depends(sec.roles("admin", "quimico"))):
    return out(await extras.guardar(db, get_o(db, id), d.resultados, u["sub"]))

@app.put("/api/ordenes/{id}/estado")
async def cambiar_estado(id: int, d: EstadoIn, db=Depends(get_db), u=Depends(sec.roles("admin", "quimico"))):
    o = get_o(db, id)
    if d.estado not in logic.TRANS.get(o.estado, []):
        raise HTTPException(422, f"No se puede pasar de {o.estado} a {d.estado}")
    if d.estado in ("Validación", "Entregado") and not o.resultados:
        raise HTTPException(422, "Captura los resultados antes de avanzar")
    prev = o.estado; o.estado = d.estado
    audit(db, u["sub"], f"Estado → {d.estado}", o.folio, {"estado": prev}, {"estado": d.estado})
    db.commit(); db.refresh(o)
    if d.estado == "Entregado" and o.prioridad == 1:
        await hub.alert({"nivel": "critico", "folio": o.folio, "paciente": o.paciente.nombre,
                         "mensaje": f"Resultado crítico entregado: avisar al médico ({o.solicitante or 'sin asignar'})"})
    return out(o)

@app.get("/api/stats")
def stats(db=Depends(get_db), u=Depends(sec.user)):
    base = db.query(m.Orden).filter(m.Orden.eliminado == False)
    est = dict(base.with_entities(m.Orden.estado, func.count()).group_by(m.Orden.estado).all())
    crit = base.filter(m.Orden.prioridad == 1, m.Orden.estado != "Entregado").count()
    return {"estados": est, "criticas": crit, "total": sum(est.values())}

@app.get("/api/auditoria")
def auditoria(db=Depends(get_db), u=Depends(sec.roles("admin"))):
    r = db.query(m.Auditoria).order_by(m.Auditoria.id.desc()).limit(200).all()
    return [{"fecha": a.fecha.isoformat(), "usuario": a.usuario, "accion": a.accion, "folio": a.folio} for a in r]

# ---------- Datos de demostración (solo si la BD está vacía) ----------
def seed():
    db = m.SessionLocal()
    if db.query(m.Usuario).count():
        db.close(); return
    for un, nom, rol in [("admin", "Administrador OCAC", "admin"), ("dra.lopez", "Dra. Mariana López", "medico"),
                         ("qfb.ramirez", "QFB Luis Ramírez", "quimico"), ("recepcion", "Ana Torres", "recepcion")]:
        db.add(m.Usuario(username=un, nombre=nom, rol=rol, hashed_password=sec.hash_pw("Ocac2026!")))
    pac = [("EXP-0001", "Carlos Hernández Ruiz", "M", "1958-03-12"), ("EXP-0002", "María Fernanda Soto", "F", "1990-07-25"),
           ("EXP-0003", "José Luis Morales", "M", "1972-11-02"), ("EXP-0004", "Guadalupe Ortega", "F", "1965-01-30"),
           ("EXP-0005", "Ricardo Flores", "M", "2001-09-14"), ("EXP-0006", "Sofía Cabrera", "F", "1984-05-19")]
    ps = []
    for e, n, s, f in pac:
        p = m.Paciente(expediente=e, nombre=n, sexo=s, fecha_nac=f); db.add(p); ps.append(p)
    db.flush()
    B, Q, E = "Biometría hemática", "Química sanguínea", "Electrolitos séricos"
    datos = [  # (paciente, análisis, prioridad, estado, resultados, solicitante)
        (0, "Troponina I", 1, "Procesando", {"Troponina I": 0.85}, "Dra. López · Urgencias"),
        (1, B, 3, "Entregado", {"Hemoglobina": 13.1, "Leucocitos": 6.8, "Plaquetas": 260}, "Dra. López"),
        (2, Q, 2, "Validación", {"Glucosa": 182, "Creatinina": 1.1, "Urea": 38}, "Dr. Vega · Medicina interna"),
        (3, "Perfil de lípidos", 3, "Entregado", {"Colesterol total": 238, "Triglicéridos": 190, "HDL": 45}, "Dra. López"),
        (4, E, 2, "Procesando", {"Sodio": 131, "Potasio": 5.8, "Cloro": 99}, "Dr. Vega"),
        (5, "Hemoglobina glucosilada", 3, "Recepcionado", None, "Dra. López"),
        (0, "Tiempos de coagulación", 2, "Recepcionado", None, "Dr. Vega · UCI"),
        (2, B, 1, "Procesando", {"Hemoglobina": 6.4, "Leucocitos": 12.5, "Plaquetas": 90}, "Dr. Vega · UCI"),
        (1, "Perfil de lípidos", 3, "Recepcionado", None, "Dra. López"),
        (3, Q, 3, "Validación", {"Glucosa": 96, "Creatinina": 0.9, "Urea": 30}, "Dra. López"),
    ]
    for i, (pi, tipo, pr, est, res, sol) in enumerate(datos, 1):
        o = m.Orden(folio=f"OC-DEMO-{i:05d}", paciente_id=ps[pi].id, tipo_analisis=tipo, prioridad=pr,
                    estado=est, resultados=res, solicitante=sol)
        db.add(o)
    B, Q = "Biometría hemática", "Química sanguínea"  # historial de José Luis Morales (tendencias y delta-check)
    for d, hb, gl in [(30, 13.8, 110), (14, 12.1, 135), (7, 10.2, 150)]:
        for t, r in [(B, {"Hemoglobina": hb, "Leucocitos": 7.1, "Plaquetas": 230}), (Q, {"Glucosa": gl, "Creatinina": 1.0, "Urea": 33})]:
            db.add(m.Orden(folio=f"OC-HIST-{t[0]}{d:03d}", paciente_id=ps[2].id, tipo_analisis=t, prioridad=3,
                           estado="Entregado", resultados=r, solicitante="Dr. Vega", creado=m.now() - timedelta(days=d)))
    db.commit(); db.close()
seed()

app.include_router(extras.router)
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="web")
