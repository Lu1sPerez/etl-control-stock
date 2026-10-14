"""Configuración del pipeline: rutas y formato de archivo de cada sucursal."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ / "data" / "entrada"
REFERENCIA = RAIZ / "data" / "referencia"
STAGING = RAIZ / "data" / "staging"
RECHAZADOS = RAIZ / "data" / "rechazados"
WAREHOUSE = RAIZ / "data" / "warehouse" / "stock.db"
REPORTES = RAIZ / "reportes"

# Umbral a partir del cual una diferencia entre stock físico y de sistema se investiga
UMBRAL_DIFERENCIA_PCT = 5.0

# Cada sucursal exporta con su propio formato. Agregar una sucursal nueva = agregar una entrada acá.
FORMATOS = {
    "CENTRO": {
        "lectura": {"sep": ";", "encoding": "utf-8"},
        "columnas": {"codigo": "codigo", "cantidad": "cantidad", "fecha": "fecha"},
        "decimal_coma": True,
        "formato_fecha": "%d/%m/%Y",
    },
    "CITYBELL": {
        "lectura": {"sep": ",", "encoding": "utf-8"},
        "columnas": {"SKU": "codigo", "Qty": "cantidad", "Date": "fecha"},
        "decimal_coma": False,
        "formato_fecha": "%Y-%m-%d",
    },
    "GONNET": {
        "lectura": {"sep": ",", "encoding": "utf-8"},
        "columnas": {"cod_producto": "codigo", "cant": "cantidad", "unidad": "unidad_origen",
                     "fecha_conteo": "fecha"},
        "decimal_coma": False,
        "formato_fecha": "%d-%m-%Y",
    },
    "LOSHORNOS": {
        "lectura": {"sep": ",", "encoding": "latin-1", "skiprows": 1},
        "columnas": {"Código": "codigo", "Cantidad contada": "cantidad", "Fecha": "fecha"},
        "decimal_coma": False,
        "formato_fecha": "%d/%m/%Y",
    },
}

# Conversión de unidades de origen a la unidad del catálogo
CONVERSION_UNIDADES = {"g": 0.001, "kg": 1.0, "ml": 0.001, "l": 1.0, "u": 1.0}
