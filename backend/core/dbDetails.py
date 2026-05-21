"""Database connection details loaded from .env (matches production pattern)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

database_details = (
    "Driver={" + os.getenv("DB_DRIVER", "SQL Server") + "};"
    "Server=" + os.getenv("DB_SERVER", "") + ";"
    "Database=" + os.getenv("DB_NAME", "") + ";"
    "uid=" + os.getenv("DB_USER", "") + ";"
    "pwd=" + os.getenv("DB_PASSWORD", "") + ";"
    "TrustServerCertificate=yes"
)
