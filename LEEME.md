# OCAC - Instalación rápida
1. Borra y vuelve a crear la base `ocac_db` en pgAdmin (el esquema cambió).
2. Edita la línea `URL` de models.py con tu contraseña de PostgreSQL.
3. Con el venv activo: pip install -r requirements.txt
4. uvicorn main:app --reload   ->  abre http://127.0.0.1:8000
Usuarios demo (contraseña Ocac2026!): admin, dra.lopez, qfb.ramirez, recepcion
API docs: http://127.0.0.1:8000/docs
