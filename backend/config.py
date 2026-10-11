import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv('STUDIO_DATA_DIR', str(ROOT / 'data')))
PUBLIC_BASE_URL = os.getenv('STUDIO_PUBLIC_BASE_URL', '').rstrip('/')
SECURE_COOKIE = os.getenv('STUDIO_SECURE_COOKIE', 'false').lower() == 'true'
