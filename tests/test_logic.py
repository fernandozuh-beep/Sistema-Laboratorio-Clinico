"""Pruebas de la lógica pura: rangos de referencia, valores críticos y transiciones."""
import logic


def flag(tipo, param, valor):
    return logic.evaluar(tipo, {param: valor})[param]["flag"]


def test_valores_criticos():
    assert flag("Electrolitos séricos", "Potasio", 7.8) == "crítico"   # cmax 6.5
    assert flag("Electrolitos séricos", "Potasio", 2.0) == "crítico"   # cmin 2.5
    assert flag("Química sanguínea", "Glucosa", 30) == "crítico"       # cmin 40
    assert flag("Química sanguínea", "Glucosa", 620) == "crítico"      # cmax 500
    assert flag("Biometría hemática", "Hemoglobina", 6.4) == "crítico"  # cmin 7
    assert flag("Troponina I", "Troponina I", 0.85) == "crítico"       # cmax 0.4


def test_fuera_de_rango_sin_ser_critico():
    assert flag("Electrolitos séricos", "Potasio", 5.8) == "alto"
    assert flag("Electrolitos séricos", "Potasio", 3.0) == "bajo"
    assert flag("Química sanguínea", "Glucosa", 130) == "alto"


def test_valores_normales_y_vacios():
    assert flag("Electrolitos séricos", "Potasio", 4.4) == "normal"
    assert flag("Química sanguínea", "Glucosa", 95) == "normal"
    assert logic.evaluar("Química sanguínea", {})["Glucosa"]["flag"] is None
    assert logic.evaluar("Química sanguínea", None)["Glucosa"]["valor"] is None


def test_hay_critico():
    assert logic.hay_critico("Electrolitos séricos", {"Potasio": 7.8}) is True
    assert logic.hay_critico("Electrolitos séricos", {"Potasio": 4.4}) is False
    assert logic.hay_critico("Electrolitos séricos", {}) is False


def test_transiciones_definidas():
    assert logic.TRANS["Entregado"] == []                       # entregado queda bloqueado
    assert "Entregado" not in logic.TRANS["Recepcionado"]       # no se puede saltar el flujo
    assert "Validación" not in logic.TRANS["Recepcionado"]
    assert logic.TRANS["Recepcionado"] == ["Procesando"]
    assert "Entregado" in logic.TRANS["Validación"]
