from __future__ import annotations

from app import create_app

app = create_app()

if __name__ == "__main__":
    import os

    port = int(os.getenv("INTEGRITYSHIELD_PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
