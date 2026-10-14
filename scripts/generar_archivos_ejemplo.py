"""
Genera archivos de ejemplo "como llegan en la vida real": cada sucursal exporta su conteo
de stock con un formato distinto y con errores típicos de carga manual.

- Centro:     separador ';', decimales con coma, fechas dd/mm/aaaa
- City Bell:  separador ',', columnas en inglés, fechas aaaa-mm-dd
- Gonnet:     cantidades en gramos para productos que se miden en kg
- Los Hornos: codificación latin-1, una fila de título antes del encabezado

Errores inyectados: códigos en minúscula o con espacios, filas duplicadas, cantidades negativas,
celdas vacías, productos inexistentes y fechas mal escritas.

    python scripts/generar_archivos_ejemplo.py
"""
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ / "data" / "entrada"
REFERENCIA = RAIZ / "data" / "referencia"
rng = np.random.default_rng(11)

PRODUCTOS = [
    # codigo, descripcion, unidad, consumo diario medio por sucursal, punto de pedido, stock objetivo
    ("HAR-001", "Harina 000", "kg", 18.0, 40, 120),
    ("MAN-002", "Manteca", "kg", 6.0, 15, 45),
    ("AZU-003", "Azúcar", "kg", 7.5, 20, 60),
    ("LEC-004", "Leche entera", "l", 32.0, 60, 160),
    ("HUE-005", "Huevos", "u", 90.0, 180, 540),
    ("CAF-006", "Café en grano", "kg", 2.4, 6, 18),
    ("TEH-007", "Té en hebras", "kg", 0.6, 2, 5),
    ("QUE-008", "Queso tybo", "kg", 3.2, 8, 24),
    ("JAM-009", "Jamón cocido", "kg", 2.8, 7, 21),
    ("VAS-010", "Vaso descartable 12oz", "u", 140.0, 300, 1200),
    ("LIM-011", "Limón", "kg", 2.0, 5, 15),
    ("POL-012", "Pechuga de pollo", "kg", 3.5, 8, 25),
]
SUCURSALES = ["CENTRO", "CITYBELL", "GONNET", "LOSHORNOS"]
FACTOR = {"CENTRO": 1.3, "CITYBELL": 1.0, "GONNET": 0.85, "LOSHORNOS": 0.7}
DIAS = [date(2025, 3, 10) + timedelta(days=i) for i in range(7)]


def escribir_referencias() -> None:
    REFERENCIA.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(PRODUCTOS, columns=["codigo", "descripcion", "unidad", "consumo_diario", "punto_pedido",
                                     "stock_objetivo"]).drop(columns="consumo_diario").to_csv(
        REFERENCIA / "catalogo.csv", index=False)
    pd.DataFrame({"sucursal_id": SUCURSALES,
                  "nombre": ["Centro", "City Bell", "Gonnet", "Los Hornos"]}).to_csv(
        REFERENCIA / "sucursales.csv", index=False)


def simular_stock() -> dict:
    """Stock teórico (sistema) y físico (conteo) por día. El físico tiene faltantes por mermas no registradas."""
    estado = {}
    for s in SUCURSALES:
        stock = {p[0]: p[5] * FACTOR[s] for p in PRODUCTOS}
        for d in DIAS:
            filas = []
            for cod, _, unidad, consumo, pp, obj in PRODUCTOS:
                venta = max(0, rng.normal(consumo * FACTOR[s], consumo * FACTOR[s] * 0.2))
                stock[cod] -= venta
                if stock[cod] < pp * FACTOR[s] and rng.random() < 0.7:  # a veces la reposición se demora
                    stock[cod] = obj * FACTOR[s]
                teorico = max(stock[cod], 0)
                # merma no registrada: más alta en perecederos y en Los Hornos
                tasa_merma = 0.03 if unidad in ("kg", "l") else 0.01
                tasa_merma *= 2.2 if s == "LOSHORNOS" else 1
                fisico = max(0.0, teorico * (1 - abs(rng.normal(tasa_merma, tasa_merma / 2))))
                decimales = 0 if unidad == "u" else 2
                filas.append((cod, round(teorico, decimales), round(fisico, decimales)))
            estado[(s, d)] = filas
    return estado


def con_errores(df: pd.DataFrame, col_cod: str, col_cant: str) -> pd.DataFrame:
    df = df.copy()
    i = rng.integers(len(df))
    df.loc[i, col_cod] = f" {str(df.loc[i, col_cod]).lower()} "        # código mal tipeado
    if rng.random() < 0.6:
        df = pd.concat([df, df.iloc[[rng.integers(len(df))]]])          # fila duplicada
    if rng.random() < 0.4:
        df.iloc[rng.integers(len(df)), df.columns.get_loc(col_cant)] = -abs(df[col_cant].iloc[0])
    if rng.random() < 0.4:
        df.iloc[rng.integers(len(df)), df.columns.get_loc(col_cant)] = np.nan
    if rng.random() < 0.3:
        extra = df.iloc[[0]].copy()
        extra[col_cod] = "XXX-999"                                        # producto inexistente
        df = pd.concat([df, extra])
    return df.reset_index(drop=True)


def main() -> None:
    ENTRADA.mkdir(parents=True, exist_ok=True)
    for f in ENTRADA.glob("*.csv"):
        f.unlink()
    escribir_referencias()
    estado = simular_stock()
    desc = {p[0]: p[1] for p in PRODUCTOS}
    unidad = {p[0]: p[2] for p in PRODUCTOS}

    for d in DIAS:
        # 1) Export del sistema de gestión (stock teórico), formato limpio
        sistema = [(s, cod, teo) for s in SUCURSALES for cod, teo, _ in estado[(s, d)]]
        pd.DataFrame(sistema, columns=["sucursal_id", "codigo", "stock_teorico"]).assign(
            fecha=d.isoformat()).to_csv(ENTRADA / f"sistema_stock_{d:%Y%m%d}.csv", index=False)

        # 2) Conteos físicos, uno por sucursal y cada uno con su formato
        filas = estado[("CENTRO", d)]
        df = pd.DataFrame({"codigo": [f[0] for f in filas], "descripcion": [desc[f[0]] for f in filas],
                           "cantidad": [f[2] for f in filas], "fecha": d.strftime("%d/%m/%Y")})
        df = con_errores(df, "codigo", "cantidad")
        df["cantidad"] = df["cantidad"].map(lambda x: "" if pd.isna(x) else str(x).replace(".", ","))
        df.to_csv(ENTRADA / f"conteo_CENTRO_{d:%Y%m%d}.csv", sep=";", index=False)

        filas = estado[("CITYBELL", d)]
        df = pd.DataFrame({"SKU": [f[0] for f in filas], "Product": [desc[f[0]] for f in filas],
                           "Qty": [f[2] for f in filas], "Date": d.isoformat()})
        df = con_errores(df, "SKU", "Qty")
        if d.day == 13:
            df.loc[2, "Date"] = "2025-13-03"                               # fecha inválida
        df.to_csv(ENTRADA / f"conteo_CITYBELL_{d:%Y%m%d}.csv", index=False)

        filas = estado[("GONNET", d)]
        df = pd.DataFrame({"cod_producto": [f[0] for f in filas],
                           "cant": [f[2] * 1000 if unidad[f[0]] == "kg" else f[2] for f in filas],
                           "unidad": ["g" if unidad[f[0]] == "kg" else unidad[f[0]] for f in filas],
                           "fecha_conteo": d.strftime("%d-%m-%Y")})
        df = con_errores(df, "cod_producto", "cant")
        df.to_csv(ENTRADA / f"conteo_GONNET_{d:%Y%m%d}.csv", index=False)

        if d.day == 14:
            continue  # Los Hornos no envió el archivo ese día: el pipeline debe detectarlo
        filas = estado[("LOSHORNOS", d)]
        df = pd.DataFrame({"Código": [f[0] for f in filas], "Descripción": [desc[f[0]] for f in filas],
                           "Cantidad contada": [f[2] for f in filas], "Fecha": d.strftime("%d/%m/%Y")})
        df = con_errores(df, "Código", "Cantidad contada")
        ruta = ENTRADA / f"conteo_LOSHORNOS_{d:%Y%m%d}.csv"
        with open(ruta, "w", encoding="latin-1", newline="") as f:
            f.write("Planilla de conteo semanal - Sucursal Los Hornos\n")
            df.to_csv(f, index=False)

    print(f"Archivos generados en {ENTRADA}: {len(list(ENTRADA.glob('*.csv')))}")


if __name__ == "__main__":
    main()
