"""Pruebas de la API: autenticación, roles, flujo de estados, acuse y exportaciones.
Corren contra la semilla demo en una base temporal (ver conftest.py)."""
from conftest import orden_por_folio

NUEVA = {"expediente": "EXP-PRUEBA-1", "nombre": "Paciente De Prueba", "sexo": "M",
         "fecha_nac": "1990-05-01", "tipo_analisis": "Química sanguínea",
         "prioridad": 3, "solicitante": "Dr. Prueba"}


def test_login_clave_incorrecta(client):
    r = client.post("/api/auth/login", data={"username": "admin", "password": "no-es-esta"})
    assert r.status_code == 401


def test_sin_token_no_hay_acceso(client):
    assert client.get("/api/ordenes").status_code == 401
    assert client.get("/api/stats").status_code == 401


def test_lista_de_ordenes(client, admin):
    r = client.get("/api/ordenes", headers=admin)
    assert r.status_code == 200
    folios = [o["folio"] for o in r.json()]
    assert "OC-DEMO-00001" in folios and "OC-DEMO-00008" in folios
    o = orden_por_folio(client, admin, "OC-DEMO-00001")
    assert o["analisis"]["Troponina I"]["flag"] == "crítico"
    assert "acuses" in o


def test_stats(client, admin):
    r = client.get("/api/stats", headers=admin)
    assert r.status_code == 200 and r.json()["total"] >= 16


def test_crear_orden_segun_rol(client, recepcion, quimico):
    r = client.post("/api/ordenes", json=NUEVA, headers=recepcion)
    assert r.status_code == 201 and r.json()["folio"].startswith("OC-")
    r = client.post("/api/ordenes", json=NUEVA, headers=quimico)
    assert r.status_code == 403  # el químico no crea órdenes


def test_flujo_de_estados(client, recepcion, quimico):
    oid = client.post("/api/ordenes", json=NUEVA, headers=recepcion).json()["id"]

    def mover(estado):
        return client.put(f"/api/ordenes/{oid}/estado", json={"estado": estado}, headers=quimico)

    assert mover("Entregado").status_code == 422    # no se puede saltar el flujo
    assert mover("Validación").status_code == 422   # tampoco directo a validación
    assert mover("Procesando").status_code == 200
    assert mover("Validación").status_code == 422   # sin resultados no valida
    r = client.put(f"/api/ordenes/{oid}/resultados", headers=quimico,
                   json={"resultados": {"Glucosa": 95, "Creatinina": 1.0, "Urea": 30}})
    assert r.status_code == 200
    assert mover("Validación").status_code == 200
    assert mover("Entregado").status_code == 200
    assert mover("Procesando").status_code == 422   # entregado queda bloqueado


def test_captura_solo_quimico_o_admin(client, recepcion, admin):
    o = orden_por_folio(client, admin, "OC-DEMO-00003")
    r = client.put(f"/api/ordenes/{o['id']}/resultados", headers=recepcion,
                   json={"resultados": {"Glucosa": 100}})
    assert r.status_code == 403


def test_acuse_de_alerta_critica(client, admin, medico, recepcion):
    o = orden_por_folio(client, admin, "OC-DEMO-00001")
    url = f"/api/ordenes/{o['id']}/acuse"
    r = client.post(url, json={"parametro": "Troponina I"}, headers=recepcion)
    assert r.status_code == 403                     # recepción no acusa
    r = client.post(url, json={"parametro": "Troponina I"}, headers=medico)
    assert r.status_code == 200 and r.json()["ok"] is True
    r = client.post(url, json={"parametro": "Troponina I"}, headers=admin)
    assert r.status_code == 200 and r.json().get("repetido") is True   # idempotente
    o = orden_por_folio(client, admin, "OC-DEMO-00001")
    assert "Troponina I" in o["acuses"] and o["acuses"]["Troponina I"]["por"]


def test_acuse_rechazos(client, admin):
    o = orden_por_folio(client, admin, "OC-DEMO-00008")
    r = client.post(f"/api/ordenes/{o['id']}/acuse", json={"parametro": "Plaquetas"}, headers=admin)
    assert r.status_code == 422                     # Plaquetas no está en crítico
    o = orden_por_folio(client, admin, "OC-DEMO-00004")
    r = client.post(f"/api/ordenes/{o['id']}/acuse", json={"parametro": "Colesterol total"}, headers=admin)
    assert r.status_code == 422                     # la orden ya fue entregada


def test_pdf_y_fhir(client, admin):
    o = orden_por_folio(client, admin, "OC-DEMO-00001")
    r = client.get(f"/api/ordenes/{o['id']}/pdf", headers=admin)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content[:4] == b"%PDF"
    r = client.get(f"/api/ordenes/{o['id']}/fhir", headers=admin)
    assert r.status_code == 200 and "resourceType" in r.json()


def test_historial(client, admin):
    o = orden_por_folio(client, admin, "OC-DEMO-00008")
    r = client.get(f"/api/ordenes/{o['id']}/historial", headers=admin)
    assert r.status_code == 200
    assert "series" in r.json() and "delta" in r.json()


def test_eliminar_solo_admin(client, recepcion, medico, admin):
    oid = client.post("/api/ordenes", json=NUEVA, headers=recepcion).json()["id"]
    assert client.delete(f"/api/ordenes/{oid}", headers=medico).status_code == 403
    assert client.delete(f"/api/ordenes/{oid}", headers=admin).status_code == 200


def test_usuarios_solo_admin(client, medico, admin):
    assert client.get("/api/usuarios", headers=medico).status_code == 403
    assert client.get("/api/usuarios", headers=admin).status_code == 200


def test_bloqueo_tras_cinco_intentos(client, admin):
    r = client.post("/api/usuarios", headers=admin, json={
        "username": "prueba.bloqueo", "nombre": "Usuario Para Bloqueo",
        "rol": "recepcion", "password": "ClaveSegura1"})
    assert r.status_code == 201
    for _ in range(5):
        r = client.post("/api/auth/login", data={"username": "prueba.bloqueo", "password": "incorrecta"})
        assert r.status_code == 401
    r = client.post("/api/auth/login", data={"username": "prueba.bloqueo", "password": "ClaveSegura1"})
    assert r.status_code == 429                     # bloqueada aunque la clave sea correcta
