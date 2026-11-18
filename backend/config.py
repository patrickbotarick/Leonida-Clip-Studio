import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get('LEONIDA_DATA_DIR') or ROOT / '.local').resolve()
DATA.mkdir(parents=True, exist_ok=True)
VERSION = '0.1.0'
