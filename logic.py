# Catálogo con rangos de referencia (adulto) y valores críticos (pánico). u=unidad
P = lambda u, a, b, ca=None, cb=None: {"u": u, "min": a, "max": b, "cmin": ca, "cmax": cb}
CATALOGO = {
    "Biometría hemática": {"area": "Hematología", "params": {
        "Hemoglobina": P("g/dL", 12, 17.5, 7, 20), "Leucocitos": P("10³/µL", 4, 11, 2, 30),
        "Plaquetas": P("10³/µL", 150, 450, 20, 1000)}},
    "Química sanguínea": {"area": "Química clínica", "params": {
        "Glucosa": P("mg/dL", 70, 100, 40, 500), "Creatinina": P("mg/dL", 0.6, 1.3, None, 5),
        "Urea": P("mg/dL", 15, 45, None, 200)}},
    "Perfil de lípidos": {"area": "Química clínica", "params": {
        "Colesterol total": P("mg/dL", 0, 200), "Triglicéridos": P("mg/dL", 0, 150, None, 1000),
        "HDL": P("mg/dL", 40, 90)}},
    "Electrolitos séricos": {"area": "Química clínica", "params": {
        "Sodio": P("mmol/L", 135, 145, 120, 160), "Potasio": P("mmol/L", 3.5, 5.1, 2.5, 6.5),
        "Cloro": P("mmol/L", 98, 107)}},
    "Troponina I": {"area": "Urgencias", "params": {"Troponina I": P("ng/mL", 0, 0.04, None, 0.4)}},
    "Tiempos de coagulación": {"area": "Hematología", "params": {
        "INR": P("", 0.8, 1.2, None, 5), "TP": P("seg", 11, 13.5), "TTPa": P("seg", 25, 35)}},
    "Hemoglobina glucosilada": {"area": "Química clínica", "params": {"HbA1c": P("%", 4, 5.6, None, 14)}},
}
ESTADOS = ["Recepcionado", "Procesando", "Validación", "Entregado"]
TRANS = {"Recepcionado": ["Procesando"], "Procesando": ["Validación", "Recepcionado"],
         "Validación": ["Entregado", "Procesando"], "Entregado": []}  # Entregado queda bloqueado

def evaluar(tipo, valores):
    """Devuelve cada parámetro con su bandera: normal | bajo | alto | crítico."""
    out = {}
    for k, p in CATALOGO.get(tipo, {}).get("params", {}).items():
        v = (valores or {}).get(k)
        if v is None:
            out[k] = {**p, "valor": None, "flag": None}
            continue
        if (p["cmin"] is not None and v < p["cmin"]) or (p["cmax"] is not None and v > p["cmax"]):
            f = "crítico"
        else:
            f = "bajo" if v < p["min"] else "alto" if v > p["max"] else "normal"
        out[k] = {**p, "valor": v, "flag": f}
    return out

def hay_critico(tipo, valores):
    return any(x["flag"] == "crítico" for x in evaluar(tipo, valores).values())
