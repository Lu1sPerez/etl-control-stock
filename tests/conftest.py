import sys
from pathlib import Path

# Permite `from etl import ...` y `from scripts import ...` al correr pytest desde la raíz
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
