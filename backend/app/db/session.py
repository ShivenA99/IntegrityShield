from __future__ import annotations

from contextlib import contextmanager

from ..extensions import db


@contextmanager
def session_scope():
    session = db.session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
