"""Připojení k PostgreSQL podle proměnných z .env."""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine


def db_url(env: dict | None = None) -> URL:
    """Sestaví URL pro SQLAlchemy z proměnných prostředí (nebo z předaného slovníku)."""
    if env is None:
        load_dotenv()
        env = dict(os.environ)
    return URL.create(
        drivername="postgresql+psycopg2",
        username=env.get("POSTGRES_USER", "firemni"),
        password=env.get("POSTGRES_PASSWORD"),
        host=env.get("POSTGRES_HOST", "localhost"),
        port=int(env.get("POSTGRES_PORT", "5432")),
        database=env.get("POSTGRES_DB", "firemni_databaze"),
    )


def get_engine() -> Engine:
    return create_engine(db_url())
