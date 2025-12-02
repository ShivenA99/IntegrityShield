from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import text

from ...extensions import db


class DatabaseInspector:
    def run_query(self, sql: str, params: dict[str, Any] | None = None) -> Sequence[dict[str, Any]]:
        statement = text(sql)
        result = db.session.execute(statement, params or {})
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result.fetchall()]
