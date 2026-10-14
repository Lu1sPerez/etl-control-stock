"""Carga en el data warehouse (SQLite). Idempotente: reprocesar un día reemplaza ese día, no lo duplica."""
import sqlite3
from contextlib import closing
from datetime import date

import pandas as pd

from etl import config

DDL = """
CREATE TABLE IF NOT EXISTS dim_producto (
    codigo TEXT PRIMARY KEY, descripcion TEXT, unidad TEXT, punto_pedido REAL, stock_objetivo REAL
);
CREATE TABLE IF NOT EXISTS dim_sucursal (sucursal_id TEXT PRIMARY KEY, nombre TEXT);
CREATE TABLE IF NOT EXISTS fact_stock_diario (
    fecha TEXT NOT NULL, sucursal_id TEXT NOT NULL, codigo TEXT NOT NULL,
    stock_fisico REAL, stock_teorico REAL, diferencia REAL, diferencia_pct REAL,
    alerta_diferencia INTEGER, alerta_reposicion INTEGER, cantidad_sugerida REAL,
    PRIMARY KEY (fecha, sucursal_id, codigo)
);
CREATE TABLE IF NOT EXISTS rechazos (
    fecha_proceso TEXT, archivo TEXT, fila INTEGER, sucursal_id TEXT, codigo TEXT,
    cantidad_raw TEXT, fecha_raw TEXT, motivo TEXT
);
CREATE TABLE IF NOT EXISTS log_ejecuciones (
    fecha_proceso TEXT, ejecutado_en TEXT, filas_leidas INTEGER, filas_validas INTEGER,
    filas_rechazadas INTEGER, sucursales_faltantes TEXT, estado TEXT
);
"""


def conectar(ruta=None) -> sqlite3.Connection:
    # la ruta se resuelve al llamar (no al importar) para poder redirigirla en tests
    ruta = ruta or config.WAREHOUSE
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.executescript(DDL)
    return con


def cargar_dimensiones(catalogo: pd.DataFrame, sucursales: pd.DataFrame, ruta=None) -> None:
    with closing(conectar(ruta)) as con, con:
        con.execute("DELETE FROM dim_producto")
        con.execute("DELETE FROM dim_sucursal")
        catalogo.to_sql("dim_producto", con, if_exists="append", index=False)
        sucursales.to_sql("dim_sucursal", con, if_exists="append", index=False)


def cargar_dia(fecha: date, hechos: pd.DataFrame, rechazados: pd.DataFrame, log: dict,
               ruta=None) -> None:
    f = fecha.isoformat()
    hechos = hechos.assign(fecha=f).drop(columns=["descripcion", "unidad"])
    rech = rechazados.assign(fecha_proceso=f)[
        ["fecha_proceso", "archivo", "fila", "sucursal_id", "codigo", "cantidad_raw", "fecha_raw", "motivo"]]
    with closing(conectar(ruta)) as con, con:  # una sola transacción: todo o nada
        con.execute("DELETE FROM fact_stock_diario WHERE fecha = ?", (f,))
        con.execute("DELETE FROM rechazos WHERE fecha_proceso = ?", (f,))
        hechos.to_sql("fact_stock_diario", con, if_exists="append", index=False)
        rech.to_sql("rechazos", con, if_exists="append", index=False)
        pd.DataFrame([log]).to_sql("log_ejecuciones", con, if_exists="append", index=False)
