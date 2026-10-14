"""Transformación: unidades homogéneas, conciliación físico vs sistema y sugerencia de reposición."""
import numpy as np
import pandas as pd

from etl import config


def convertir_unidades(validos: pd.DataFrame, catalogo: pd.DataFrame) -> pd.DataFrame:
    df = validos.merge(catalogo[["codigo", "unidad"]], on="codigo", how="left")
    origen = df["unidad_origen"].replace("", np.nan).fillna(df["unidad"])
    factor = origen.map(config.CONVERSION_UNIDADES)
    if factor.isna().any():
        desconocidas = sorted(origen[factor.isna()].unique())
        raise ValueError(f"Unidades sin regla de conversión: {desconocidas}")
    df["stock_fisico"] = (df["cantidad"] * factor).round(3)
    return df


def conciliar(fisico: pd.DataFrame, sistema: pd.DataFrame, catalogo: pd.DataFrame) -> pd.DataFrame:
    df = fisico.merge(sistema[["sucursal_id", "codigo", "stock_teorico"]], on=["sucursal_id", "codigo"], how="left")
    df = df.merge(catalogo[["codigo", "descripcion", "punto_pedido", "stock_objetivo"]], on="codigo", how="left")

    df["diferencia"] = (df["stock_fisico"] - df["stock_teorico"]).round(3)
    df["diferencia_pct"] = np.where(df["stock_teorico"] > 0,
                                    100 * df["diferencia"] / df["stock_teorico"], np.nan).round(2)
    df["alerta_diferencia"] = (df["diferencia_pct"].abs() > config.UMBRAL_DIFERENCIA_PCT).astype(int)
    df["alerta_reposicion"] = (df["stock_fisico"] < df["punto_pedido"]).astype(int)
    df["cantidad_sugerida"] = np.where(df["alerta_reposicion"] == 1,
                                       np.ceil(df["stock_objetivo"] - df["stock_fisico"]), 0)
    columnas = ["fecha", "sucursal_id", "codigo", "descripcion", "unidad", "stock_fisico", "stock_teorico",
                "diferencia", "diferencia_pct", "alerta_diferencia", "alerta_reposicion", "cantidad_sugerida"]
    return df[columnas].sort_values(["sucursal_id", "codigo"]).reset_index(drop=True)
