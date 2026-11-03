import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, Boolean, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# >>> CAMBIA TU_CONTRASEÑA (o define la variable de entorno DATABASE_URL)
URL = os.getenv("DATABASE_URL", "postgresql://postgres:ocac@localhost:5432/ocac_db")
engine = create_engine(URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()
now = lambda: datetime.now(timezone.utc)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    nombre = Column(String(100))
    hashed_password = Column(String, nullable=False)
    rol = Column(String(20), default="medico")  # admin | medico | quimico | recepcion
    activo = Column(Boolean, default=True)
    intentos = Column(Integer, default=0)
    bloqueado_hasta = Column(DateTime(timezone=True))

class Paciente(Base):
    __tablename__ = "pacientes"
    id = Column(Integer, primary_key=True)
    expediente = Column(String(30), unique=True, index=True, nullable=False)
    nombre = Column(String(120), nullable=False)
    sexo = Column(String(1), default="M")
    fecha_nac = Column(String(10))

class Orden(Base):
    __tablename__ = "ordenes"
    id = Column(Integer, primary_key=True)
    folio = Column(String(20), unique=True, index=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id"), index=True)
    paciente = relationship("Paciente")
    tipo_analisis = Column(String(80), nullable=False)
    estado = Column(String(20), default="Recepcionado", index=True)
    prioridad = Column(Integer, default=3)  # 1 crítica, 2 urgente, 3 rutina
    solicitante = Column(String(100), default="")
    observaciones = Column(Text, default="")
    resultados = Column(JSON)
    creado = Column(DateTime(timezone=True), default=now)
    actualizado = Column(DateTime(timezone=True), default=now, onupdate=now)
    eliminado = Column(Boolean, default=False)  # borrado lógico: nunca se pierde el rastro clínico

class Auditoria(Base):
    __tablename__ = "auditoria"
    id = Column(Integer, primary_key=True)
    usuario = Column(String(50), nullable=False)
    accion = Column(String(120), nullable=False)
    folio = Column(String(20))
    datos_previos = Column(JSON)
    datos_nuevos = Column(JSON)
    fecha = Column(DateTime(timezone=True), default=now)
