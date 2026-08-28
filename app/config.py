"""Application configuration. Secrets and runtime settings come from the environment."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'patients.db'}")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
