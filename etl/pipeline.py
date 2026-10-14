"""
Pipeline diario de control de stock.

Cada paso lee y escribe en data/staging/, así puede correr solo (para depurar) o como una tarea
independiente de Airflow (ver dags/etl_stock_dag.py).

Uso:
    python -m etl.pipeline --fecha 2025-03-12
    python -m etl.pipeline --todas          # procesa todas las fechas disponibles en data/entrada/
"""
import argparse
import json
import logging
import re
from datetime import date, datetime

import pandas as pd

from etl import cargar, config, extraer, reporte, transformar, validar

log = logging.getLogger("etl")


def _staging(fecha: date, nombre: str):
    config.STAGING.mkdir(parents=True, exist_ok=True)
    return config.STAGING / f"{fecha:%Y%m%d}_{nombre}"


def _referencias() -> tuple[pd.DataFrame, pd.DataFrame]:
    return (pd.read_csv(config.REFERENCIA / "catalogo.csv"),
            pd.read_csv(config.REFERENCIA / "sucursales.csv"))


def paso_extraer(fecha: date) -> dict:
    crudo, sistema, faltantes = extraer.extraer_dia(fecha)
    crudo.to_csv(_staging(fecha, "crudo.csv"), index=False)
    sistema.to_csv(_staging(fecha, "sistema.csv"), index=False)
    meta = {"filas_leidas": len(crudo), "sucursales_faltantes": faltantes}
    _staging(fecha, "meta.json").write_text(json.dumps(meta))
    return meta


def paso_validar(fecha: date) -> dict:
    catalogo, _ = _referencias()
    crudo = pd.read_csv(_staging(fecha, "crudo.csv"), dtype=str, keep_default_na=False)
    validos, rechazados = validar.validar(crudo, catalogo, fecha)
    validos.to_csv(_staging(fecha, "validos.csv"), index=False)
    rechazados.to_csv(_staging(fecha, "rechazados.csv"), index=False)
    config.RECHAZADOS.mkdir(parents=True, exist_ok=True)
    rechazados.to_csv(config.RECHAZADOS / f"rechazados_{fecha:%Y%m%d}.csv", index=False)
    log.info("%s: %d válidas, %d rechazadas", fecha, len(validos), len(rechazados))
    return {"filas_validas": len(validos), "filas_rechazadas": len(rechazados)}


def paso_transformar_cargar(fecha: date) -> dict:
    catalogo, sucursales = _referencias()
    validos = pd.read_csv(_staging(fecha, "validos.csv"), keep_default_na=False,
                          dtype={"unidad_origen": str, "codigo": str})
    validos["cantidad"] = pd.to_numeric(validos["cantidad"])
    rechazados = pd.read_csv(_staging(fecha, "rechazados.csv"), dtype=str, keep_default_na=False)
    sistema = pd.read_csv(_staging(fecha, "sistema.csv"))
    meta = json.loads(_staging(fecha, "meta.json").read_text())

    fisico = transformar.convertir_unidades(validos, catalogo)
    hechos = transformar.conciliar(fisico, sistema, catalogo)
    hechos.to_csv(_staging(fecha, "hechos.csv"), index=False)

    cargar.cargar_dimensiones(catalogo, sucursales)
    cargar.cargar_dia(fecha, hechos, rechazados, {
        "fecha_proceso": fecha.isoformat(),
        "ejecutado_en": datetime.now().isoformat(timespec="seconds"),
        "filas_leidas": meta["filas_leidas"],
        "filas_validas": len(validos),
        "filas_rechazadas": len(rechazados),
        "sucursales_faltantes": ",".join(meta["sucursales_faltantes"]),
        "estado": "OK con advertencias" if meta["sucursales_faltantes"] or len(rechazados) else "OK",
    })
    return {"filas_cargadas": len(hechos)}


def paso_reporte(fecha: date) -> dict:
    catalogo, _ = _referencias()
    crudo = pd.read_csv(_staging(fecha, "crudo.csv"), dtype=str, keep_default_na=False)
    hechos = pd.read_csv(_staging(fecha, "hechos.csv"))
    validos = pd.read_csv(_staging(fecha, "validos.csv"), dtype=str, keep_default_na=False)
    rechazados = pd.read_csv(_staging(fecha, "rechazados.csv"), dtype=str, keep_default_na=False)
    meta = json.loads(_staging(fecha, "meta.json").read_text())
    presentes = [s for s in config.FORMATOS if s not in meta["sucursales_faltantes"]]
    sin_contar = validar.productos_sin_contar(validos, catalogo, presentes)

    pedido = reporte.pedido_sugerido(hechos, fecha)
    reporte.reporte_calidad(fecha, crudo, hechos, rechazados, meta["sucursales_faltantes"], sin_contar)
    return {"productos_a_reponer": len(pedido), "productos_sin_contar": len(sin_contar)}


def ejecutar(fecha: date) -> dict:
    log.info("=== Procesando %s ===", fecha)
    resultado = {"fecha": fecha.isoformat()}
    for paso in (paso_extraer, paso_validar, paso_transformar_cargar, paso_reporte):
        resultado.update(paso(fecha))
    return resultado


def fechas_disponibles() -> list[date]:
    patron = re.compile(r"sistema_stock_(\d{8})\.csv")
    return sorted(datetime.strptime(m.group(1), "%Y%m%d").date()
                  for f in config.ENTRADA.glob("sistema_stock_*.csv") if (m := patron.match(f.name)))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="ETL diario de control de stock")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--fecha", type=date.fromisoformat, help="Fecha a procesar (AAAA-MM-DD)")
    grupo.add_argument("--todas", action="store_true", help="Procesar todas las fechas disponibles")
    args = parser.parse_args()

    fechas = fechas_disponibles() if args.todas else [args.fecha]
    resultados = [ejecutar(f) for f in fechas]
    print("\n" + pd.DataFrame(resultados).drop(columns="sucursales_faltantes").to_string(index=False))


if __name__ == "__main__":
    main()
