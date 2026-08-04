from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import get_settings


class MySQLRepository:
    def __init__(self):
        self.settings = get_settings()
        self._engine: Engine | None = None

    @property
    def is_available(self) -> bool:
        return self._engine is not None

    def connect(self) -> None:
        if self._engine:
            return
        settings = self.settings
        url = (
            f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}"
            f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
        )
        self._engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=settings.mysql_pool_size,
            max_overflow=settings.mysql_max_overflow,
        )

    def ping(self) -> bool:
        try:
            self.connect()
            assert self._engine is not None
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            self._engine = None
            return False
