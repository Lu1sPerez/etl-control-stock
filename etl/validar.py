"""
Validación y calidad de datos.

Cada fila sale como válida o como rechazada CON UN MOTIVO. Nada se descarta en silencio:
los rechazos se guardan para que la sucursal corrija en origen.
"""
from datetime import date

import pandas as pd

from etl import config

MOTIVOS = {
    "cantidad_invalida": "Cantidad vacía o no numérica",
    "cantidad_negativa": "Cantidad negativa",
    "fecha_invalida": "Fecha con formato inválido",
    "fecha_distinta": "La fecha no coincide con el día del archivo",
    "producto_inexistente": "Código de producto que no existe en el catálogo",
    "duplicado": "Fila duplicada (mismo producto contado dos veces)",
}


def normalizar_codigo(codigo: pd.Series) -> pd.Series:
    """' har-001 ' -> 'HAR-001'"""
    return codigo.astype(str).str.strip().str.upper().str.replace(r"\s+", "", regex=True)


def validar(crudo: pd.DataFrame, catalogo: pd.DataFrame, fecha_esperada: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = crudo.copy()
    df["codigo"] = normalizar_codigo(df["codigo"])
    df["cantidad"] = pd.to_numeric(df["cantidad_raw"], errors="coerce")

    df["fecha"] = pd.NaT
    for sucursal, fmt in config.FORMATOS.items():
        m = df["sucursal_id"] == sucursal
        df.loc[m, "fecha"] = pd.to_datetime(df.loc[m, "fecha_raw"], format=fmt["formato_fecha"], errors="coerce")
    df["fecha"] = pd.to_datetime(df["fecha"])

    # Reglas en orden de prioridad: cada fila se queda con el primer motivo que la rechaza
    df["motivo"] = None
    reglas = [
        ("cantidad_invalida", df["cantidad"].isna()),
        ("cantidad_negativa", df["cantidad"] < 0),
        ("fecha_invalida", df["fecha"].isna()),
        ("fecha_distinta", df["fecha"].notna() & (df["fecha"].dt.date != fecha_esperada)),
        ("producto_inexistente", ~df["codigo"].isin(catalogo["codigo"])),
    ]
    for motivo, mascara in reglas:
        df.loc[df["motivo"].isna() & mascara, "motivo"] = motivo

    # Duplicados: solo entre filas que pasaron las demás reglas; se conserva la primera
    ok = df["motivo"].isna()
    dup = df[ok].duplicated(["sucursal_id", "codigo"], keep="first")
    df.loc[dup[dup].index, "motivo"] = "duplicado"

    rechazados = df[df["motivo"].notna()].copy()
    rechazados["detalle"] = rechazados["motivo"].map(MOTIVOS)
    validos = df[df["motivo"].isna()].drop(columns=["motivo"])
    return validos, rechazados


def productos_sin_contar(validos: pd.DataFrame, catalogo: pd.DataFrame, sucursales: list[str]) -> pd.DataFrame:
    """Productos del catálogo que una sucursal no informó (completitud)."""
    esperado = pd.MultiIndex.from_product([sucursales, catalogo["codigo"]], names=["sucursal_id", "codigo"])
    recibido = pd.MultiIndex.from_frame(validos[["sucursal_id", "codigo"]])
    return esperado.difference(recibido).to_frame(index=False)
