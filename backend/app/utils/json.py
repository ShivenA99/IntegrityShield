from __future__ import annotations

from typing import Any

import orjson
from flask.json.provider import DefaultJSONProvider


class ORJSONProvider(DefaultJSONProvider):
    """Flask JSON provider that uses orjson for fast serialization."""

    def dumps(self, obj: Any, *, option: int | None = None, **kwargs: Any) -> str:
        opts = option or orjson.OPT_INDENT_2
        return orjson.dumps(obj, option=opts).decode()

    def loads(self, s: str | bytes | bytearray, **kwargs: Any) -> Any:
        return orjson.loads(s)
