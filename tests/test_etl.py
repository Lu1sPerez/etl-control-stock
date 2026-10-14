"""Tests del pipeline. Ejecutar con:  pytest -v"""
import sqlite3
from datetime import date

import pandas as pd
import pytest

from etl import cargar, config, pipeline, transformar, validar

FECHA = date(2025, 3, 12)
CATALOGO = pd.DataFrame({
    "codigo": ["HAR-001", "HUE-005"], "descripcion": ["Harina", "Huevos"], "unidad": ["kg", "u"],
    "punto_pedido": [40, 180], "stock_objetivo": [120, 540],
})


def crudo(**cambios) -> pd.DataFrame:
    base = {"sucursal_id": "CENTRO", "codigo": "HAR-001", "cantidad_raw": "50", "unidad_origen": "",
            "fecha_raw": "12/03/2025", "archivo": "x.csv", "fila": 2}
    base.update(cambios)
    return pd.DataFrame([base])


# ---------- validación ----------

def test_normaliza_codigos_mal_tipeados():
    assert validar.normalizar_codigo(pd.Series([" har-001 ", "Hue- 005"])).tolist() == ["HAR-001", "HUE-005"]


@pytest.mark.parametrize("cambio, motivo", [
    ({"cantidad_raw": ""}, "cantidad_invalida"),
    ({"cantidad_raw": "abc"}, "cantidad_invalida"),
    ({"cantidad_raw": "-3"}, "cantidad_negativa"),
    ({"fecha_raw": "32/13/2025"}, "fecha_invalida"),
    ({"fecha_raw": "11/03/2025"}, "fecha_distinta"),
    ({"codigo": "XXX-999"}, "producto_inexistente"),
])
def test_cada_regla_rechaza_con_su_motivo(cambio, motivo):
    validos, rechazados = validar.validar(crudo(**cambio), CATALOGO, FECHA)
    assert validos.empty
    assert rechazados["motivo"].tolist() == [motivo]


def test_fila_correcta_pasa():
    validos, rechazados = validar.validar(crudo(), CATALOGO, FECHA)
    assert len(validos) == 1 and rechazados.empty


def test_duplicado_conserva_la_primera_fila():
    df = pd.concat([crudo(cantidad_raw="50", fila=2), crudo(cantidad_raw="55", fila=9)], ignore_index=True)
    validos, rechazados = validar.validar(df, CATALOGO, FECHA)
    assert validos["cantidad"].tolist() == [50]
    assert rechazados["motivo"].tolist() == ["duplicado"]


def test_una_fila_invalida_no_cuenta_como_original_de_un_duplicado():
    # la primera fila es inválida (negativa); la segunda debe quedar como válida, no como duplicado
    df = pd.concat([crudo(cantidad_raw="-1"), crudo(cantidad_raw="40")], ignore_index=True)
    validos, rechazados = validar.validar(df, CATALOGO, FECHA)
    assert validos["cantidad"].tolist() == [40]
    assert rechazados["motivo"].tolist() == ["cantidad_negativa"]


# ---------- transformación ----------

def test_convierte_gramos_a_kilos():
    v = pd.DataFrame({"sucursal_id": ["GONNET"], "codigo": ["HAR-001"], "cantidad": [12500.0],
                      "unidad_origen": ["g"]})
    assert transformar.convertir_unidades(v, CATALOGO)["stock_fisico"].iloc[0] == 12.5


def test_unidad_desconocida_falla_en_lugar_de_cargar_basura():
    v = pd.DataFrame({"sucursal_id": ["GONNET"], "codigo": ["HAR-001"], "cantidad": [1.0],
                      "unidad_origen": ["libras"]})
    with pytest.raises(ValueError, match="libras"):
        transformar.convertir_unidades(v, CATALOGO)


def test_conciliacion_y_sugerencia_de_reposicion():
    fisico = pd.DataFrame({"fecha": [FECHA] * 2, "sucursal_id": ["CENTRO"] * 2, "codigo": ["HAR-001", "HUE-005"],
                           "unidad": ["kg", "u"], "stock_fisico": [30.0, 500.0]})
    sistema = pd.DataFrame({"sucursal_id": ["CENTRO"] * 2, "codigo": ["HAR-001", "HUE-005"],
                            "stock_teorico": [40.0, 505.0]})
    h = transformar.conciliar(fisico, sistema, CATALOGO).set_index("codigo")
    assert h.loc["HAR-001", "diferencia_pct"] == -25.0
    assert h.loc["HAR-001", "alerta_diferencia"] == 1          # -25% supera el umbral de 5%
    assert h.loc["HAR-001", "cantidad_sugerida"] == 90          # 120 - 30
    assert h.loc["HUE-005", "alerta_reposicion"] == 0           # 500 > punto de pedido 180


# ---------- integración ----------

@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Corre el pipeline completo sobre los archivos de ejemplo, en una carpeta temporal."""
    import shutil
    from scripts import generar_archivos_ejemplo as gen
    for nombre in ("ENTRADA", "REFERENCIA", "STAGING", "RECHAZADOS", "REPORTES"):
        monkeypatch.setattr(config, nombre, tmp_path / nombre.lower())
    monkeypatch.setattr(config, "WAREHOUSE", tmp_path / "stock.db")
    monkeypatch.setattr(gen, "ENTRADA", config.ENTRADA)
    monkeypatch.setattr(gen, "REFERENCIA", config.REFERENCIA)
    gen.main()
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_pipeline_es_idempotente(entorno):
    pipeline.ejecutar(FECHA)
    pipeline.ejecutar(FECHA)   # reprocesar el mismo día no debe duplicar filas
    con = sqlite3.connect(config.WAREHOUSE)
    filas = con.execute("SELECT COUNT(*) FROM fact_stock_diario WHERE fecha = ?", (FECHA.isoformat(),)).fetchone()[0]
    claves = con.execute("SELECT COUNT(DISTINCT sucursal_id || codigo) FROM fact_stock_diario").fetchone()[0]
    assert filas == claves > 0


def test_sucursal_sin_archivo_no_frena_el_proceso(entorno):
    resultado = pipeline.ejecutar(date(2025, 3, 14))   # Los Hornos no envió archivo ese día
    assert resultado["sucursales_faltantes"] == ["LOSHORNOS"]
    assert resultado["filas_cargadas"] > 0
