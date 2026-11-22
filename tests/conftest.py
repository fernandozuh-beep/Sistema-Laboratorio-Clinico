"""Configuración de pruebas: la app se importa con una base SQLite temporal
y la semilla demo (usuarios y órdenes de ejemplo). Nunca toca producción."""
import os
import tempfile

_db = os.path.join(tempfile.mkdtemp(prefix="monocac-test-"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["OCAC_SECRET"] = "secreto-solo-para-pruebas-0123456789"

import pytest
from fastapi.testclient import TestClient

import main

CLAVE_DEMO = "Ocac2026!"


@pytest.fixture(scope="session")
def client():
    return TestClient(main.app)


def _login(client, usuario, clave=CLAVE_DEMO):
    r = client.post("/api/auth/login", data={"username": usuario, "password": clave})
    assert r.status_code == 200, f"login {usuario}: {r.status_code} {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin(client):
    return _login(client, "admin")


@pytest.fixture(scope="session")
def medico(client):
    return _login(client, "dra.lopez")


@pytest.fixture(scope="session")
def quimico(client):
    return _login(client, "qfb.ramirez")


@pytest.fixture(scope="session")
def recepcion(client):
    return _login(client, "recepcion")


def orden_por_folio(client, headers, folio):
    r = client.get("/api/ordenes", headers=headers)
    assert r.status_code == 200
    for o in r.json():
        if o["folio"] == folio:
            return o
    raise AssertionError(f"folio no encontrado: {folio}")
