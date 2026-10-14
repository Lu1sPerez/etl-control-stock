"""Reportes de salida: pedido sugerido para compras y reporte de calidad de datos para cada sucursal."""
from datetime import date

import pandas as pd

from etl import config


def pedido_sugerido(hechos: pd.DataFrame, fecha: date) -> pd.DataFrame:
    p = hechos[hechos["alerta_reposicion"] == 1][
        ["sucursal_id", "codigo", "descripcion", "unidad", "stock_fisico", "cantidad_sugerida"]]
    ruta = config.REPORTES / f"pedido_sugerido_{fecha:%Y%m%d}.csv"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    p.to_csv(ruta, index=False)
    return p


def reporte_calidad(fecha: date, crudo: pd.DataFrame, hechos: pd.DataFrame, rechazados: pd.DataFrame,
                    faltantes: list[str], sin_contar: pd.DataFrame) -> str:
    total = len(crudo)
    lineas = [
        f"# Reporte de calidad y stock — {fecha:%d/%m/%Y}\n",
        f"- Filas recibidas: **{total}**",
        f"- Filas válidas: **{total - len(rechazados)}** ({100 * (total - len(rechazados)) / max(total, 1):.1f}%)",
        f"- Filas rechazadas: **{len(rechazados)}**",
        f"- Sucursales sin archivo: **{', '.join(faltantes) if faltantes else 'ninguna'}**",
        f"- Productos sin contar: **{len(sin_contar)}**",
        f"- Productos a reponer: **{int(hechos['alerta_reposicion'].sum())}**",
        f"- Diferencias físico vs sistema mayores al {config.UMBRAL_DIFERENCIA_PCT:.0f}%: "
        f"**{int(hechos['alerta_diferencia'].sum())}**\n",
    ]
    if len(rechazados):
        lineas.append("## Filas rechazadas (corregir en origen)\n")
        lineas.append("| Archivo | Fila | Código | Valor | Motivo |\n|---|---:|---|---|---|")
        orden = rechazados.assign(fila=pd.to_numeric(rechazados["fila"])).sort_values(["archivo", "fila"])
        for r in orden.itertuples():
            lineas.append(f"| {r.archivo} | {r.fila} | {r.codigo} | {r.cantidad_raw or '(vacío)'} | {r.detalle} |")
    dif = hechos[hechos["alerta_diferencia"] == 1].sort_values("diferencia_pct")
    if len(dif):
        lineas.append("\n## Diferencias de inventario a investigar\n")
        lineas.append("| Sucursal | Producto | Físico | Sistema | Diferencia |\n|---|---|---:|---:|---:|")
        for r in dif.itertuples():
            lineas.append(f"| {r.sucursal_id} | {r.descripcion} | {r.stock_fisico:g} {r.unidad} | "
                          f"{r.stock_teorico:g} {r.unidad} | {r.diferencia_pct:+.1f}% |")
    texto = "\n".join(lineas) + "\n"
    ruta = config.REPORTES / f"calidad_{fecha:%Y%m%d}.md"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return texto
