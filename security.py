import os, jwt, bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

# En producción define OCAC_SECRET como variable de entorno (mínimo 32 caracteres)
SECRET = os.getenv("OCAC_SECRET", "cambia-esta-clave-en-produccion-por-una-larga-y-aleatoria")
oauth2 = OAuth2PasswordBearer(tokenUrl="api/auth/login")

def hash_pw(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
def check_pw(p, h): return bcrypt.checkpw(p.encode(), h.encode())

def make_token(user, rol, mins=30):
    exp = datetime.now(timezone.utc) + timedelta(minutes=mins)
    return jwt.encode({"sub": user, "rol": rol, "exp": exp}, SECRET, algorithm="HS256")

def decode(t):
    try:
        return jwt.decode(t, SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Sesión inválida o expirada. Inicia sesión de nuevo.")

def user(t: str = Depends(oauth2)): return decode(t)

def roles(*permitidos):
    def dep(u=Depends(user)):
        if u["rol"] not in permitidos:
            raise HTTPException(403, "Tu rol no tiene permiso para esta acción")
        return u
    return dep
