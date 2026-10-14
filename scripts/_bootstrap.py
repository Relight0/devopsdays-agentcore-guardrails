"""Permite ejecutar los scripts como `python scripts/x.py` desde la raiz del repo."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lambdas" / "shared"))
