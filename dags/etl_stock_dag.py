"""
DAG de Apache Airflow (2.4+) que orquesta el ETL diario de control de stock.

Corre todos los días a las 07:00 (hora Argentina), después de que las sucursales suben
su conteo de cierre. Cada paso es una tarea separada: si falla la carga, se reintenta
solo ese paso sin volver a leer los archivos.

    verificar_archivos >> extraer >> validar >> transformar_y_cargar >> generar_reportes

Para probarlo localmente:
    pip install "apache-airflow==2.10.*"
    export AIRFLOW__CORE__DAGS_FOLDER=$(pwd)/dags
    airflow dags test etl_control_stock 2025-03-12
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pendulum
from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException

# Permite importar el paquete etl/ que vive en la raíz del repositorio
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from etl import config, pipeline  # noqa: E402

ARGS = {
    "owner": "datos",
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}


@dag(
    dag_id="etl_control_stock",
    description="Consolida conteos de stock de 4 sucursales, valida calidad y sugiere reposición",
    schedule="0 7 * * *",
    start_date=pendulum.datetime(2025, 3, 10, tz="America/Argentina/Buenos_Aires"),
    catchup=False,
    default_args=ARGS,
    tags=["stock", "calidad-de-datos"],
)
def etl_control_stock():

    @task
    def verificar_archivos(ds: str | None = None) -> str:
        """Falla si no llegó el export del sistema; avisa si falta alguna sucursal pero continúa."""
        fecha = date.fromisoformat(ds)
        sistema = config.ENTRADA / f"sistema_stock_{fecha:%Y%m%d}.csv"
        if not sistema.exists():
            raise AirflowSkipException(f"Sin export del sistema para {fecha}; nada que procesar")
        faltan = [s for s in config.FORMATOS
                  if not (config.ENTRADA / f"conteo_{s}_{fecha:%Y%m%d}.csv").exists()]
        if faltan:
            print(f"ADVERTENCIA: sucursales sin conteo: {faltan}")
        return ds

    @task
    def extraer(ds: str) -> dict:
        return pipeline.paso_extraer(date.fromisoformat(ds))

    @task
    def validar(ds: str, _extraccion: dict) -> dict:
        resultado = pipeline.paso_validar(date.fromisoformat(ds))
        total = resultado["filas_validas"] + resultado["filas_rechazadas"]
        if total and resultado["filas_rechazadas"] / total > 0.30:
            # Más de 30% de rechazos suele indicar que cambió el formato de un export
            raise ValueError(f"Rechazos anormalmente altos: {resultado}")
        return resultado

    @task
    def transformar_y_cargar(ds: str, _validacion: dict) -> dict:
        return pipeline.paso_transformar_cargar(date.fromisoformat(ds))

    @task
    def generar_reportes(ds: str, _carga: dict) -> dict:
        return pipeline.paso_reporte(date.fromisoformat(ds))

    ds = verificar_archivos()
    e = extraer(ds)
    v = validar(ds, e)
    c = transformar_y_cargar(ds, v)
    generar_reportes(ds, c)


etl_control_stock()
