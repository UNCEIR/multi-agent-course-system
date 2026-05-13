from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import get_settings
from models.schemas import Product


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

    def fetch_user_recent_behaviors(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        if not self.ping():
            return []
        assert self._engine is not None
        query = text(
            """
            SELECT user_id, product_id, behavior_type, category, score, created_at
            FROM user_behaviors
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT :limit
            """
        )
        with self._engine.connect() as conn:
            rows = conn.execute(query, {"user_id": user_id, "limit": limit}).mappings().all()
        return [dict(row) for row in rows]

    def fetch_products(
        self,
        limit: int,
        categories: list[str] | None = None,
        query_text: str = "",
    ) -> list[Product]:
        if not self.ping():
            return []
        assert self._engine is not None

        conditions = ["p.is_active = 1"]
        params: dict[str, Any] = {"limit": limit}
        if categories:
            placeholders = ", ".join(f":cat_{idx}" for idx, _ in enumerate(categories))
            conditions.append(f"p.category IN ({placeholders})")
            params.update({f"cat_{idx}": value for idx, value in enumerate(categories)})
        if query_text.strip():
            conditions.append(
                "(p.name LIKE :query_text OR p.category LIKE :query_text OR p.brand LIKE :query_text)"
            )
            params["query_text"] = f"%{query_text.strip()}%"

        sql = f"""
            SELECT p.product_id, p.name, p.category, p.price, p.description, p.brand, p.seller_id,
                   COALESCE(i.available_stock, 0) AS stock, p.tags_json, p.rating, p.review_count,
                   p.sales_count_30d, p.cost_price
            FROM products p
            LEFT JOIN inventory i ON i.product_id = p.product_id
            WHERE {" AND ".join(conditions)}
            ORDER BY p.sales_count_30d DESC, p.rating DESC
            LIMIT :limit
        """
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return [self._row_to_product(row) for row in rows]

    def fetch_stock_map(self, product_ids: list[str]) -> dict[str, int]:
        if not product_ids or not self.ping():
            return {}
        assert self._engine is not None
        placeholders = ", ".join(f":pid_{idx}" for idx, _ in enumerate(product_ids))
        params = {f"pid_{idx}": value for idx, value in enumerate(product_ids)}
        sql = text(
            f"""
            SELECT product_id, available_stock
            FROM inventory
            WHERE product_id IN ({placeholders})
            """
        )
        with self._engine.connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return {row["product_id"]: int(row["available_stock"]) for row in rows}

    @staticmethod
    def _row_to_product(row: dict[str, Any]) -> Product:
        tags_json = row.get("tags_json") or "[]"
        if isinstance(tags_json, str):
            tags = [tag.strip() for tag in tags_json.strip("[]").replace('"', "").split(",") if tag.strip()]
        else:
            tags = list(tags_json)

        return Product(
            product_id=row["product_id"],
            name=row["name"],
            category=row["category"],
            price=float(row["price"]),
            description=row.get("description") or "",
            brand=row.get("brand") or "",
            seller_id=row.get("seller_id") or "",
            stock=int(row.get("stock") or 0),
            tags=tags,
            rating=float(row.get("rating") or 0.0),
            review_count=int(row.get("review_count") or 0),
            sales_count_30d=int(row.get("sales_count_30d") or 0),
            cost_price=float(row.get("cost_price") or 0.0),
        )
