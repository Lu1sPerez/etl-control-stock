"""Extracción: lee los archivos de cada sucursal y los lleva a un formato común, sin validar todavía."""
import logging
from datetime import date

import pandas as pd

from etl import config

log = logging.getLogger(__name__)
COLUMNAS_ESTANDAR = ["sucursal_id", "codigo", "cantidad_raw", "unidad_origen", "fecha_raw", "archivo", "fila"]


def leer_conteo(ruta, sucursal: str) -> pd.DataFrame:
    """Lee el conteo físico de una sucursal y renombra sus columnas al estándar.

    Todo se lee como texto: convertir tipos es tarea de la validación, para poder
    registrar el motivo exacto de cada rechazo.
    """
    fmt = config.FORMATOS[sucursal]
    df = pd.read_csv(ruta, dtype=str, keep_default_na=False, **fmt["lectura"])
    faltantes = set(fmt["columnas"]) - set(df.columns)
    if faltantes:
        raise ValueError(f"{ruta.name}: faltan columnas {sorted(faltantes)} (¿cambió el formato del export?)")

    df = df.rename(columns=fmt["columnas"])
    if "unidad_origen" not in df:
        df["unidad_origen"] = ""
    cantidad = df["cantidad"].str.strip()
    if fmt["decimal_coma"]:
        cantidad = cantidad.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    out = pd.DataFrame({
        "sucursal_id": sucursal,
        "codigo": df["codigo"],
        "cantidad_raw": cantidad,
        "unidad_origen": df["unidad_origen"].str.strip().str.lower(),
        "fecha_raw": df["fecha"].str.strip(),
        "archivo": ruta.name,
        # número de fila en el archivo original (encabezado = 1), útil para corregir en origen
        "fila": df.index + 2 + fmt["lectura"].get("skiprows", 0),
    })
    return out[COLUMNAS_ESTANDAR]


def extraer_dia(fecha: date) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Devuelve (conteos crudos, stock de sistema, sucursales sin archivo) para una fecha."""
    sufijo = f"{fecha:%Y%m%d}"
    ruta_sistema = config.ENTRADA / f"sistema_stock_{sufijo}.csv"
    if not ruta_sistema.exists():
        raise FileNotFoundError(f"No llegó el export del sistema para {fecha}: {ruta_sistema.name}")
    sistema = pd.read_csv(ruta_sistema)

    partes, faltantes = [], []
    for sucursal in config.FORMATOS:
        ruta = config.ENTRADA / f"conteo_{sucursal}_{sufijo}.csv"
        if not ruta.exists():
            log.warning("Sucursal %s sin archivo de conteo para %s", sucursal, fecha)
            faltantes.append(sucursal)
            continue
        partes.append(leer_conteo(ruta, sucursal))
        log.info("Leído %s (%d filas)", ruta.name, len(partes[-1]))
    crudo = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=COLUMNAS_ESTANDAR)
    return crudo, sistema, faltantes
