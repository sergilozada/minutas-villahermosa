from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from backend.config import DATABASE_URL
from backend.database_postgres import PostgresDatabase
from backend.http_app import VillaHermosaHandler


database = PostgresDatabase(DATABASE_URL)
database.initialize()


class handler(VillaHermosaHandler):
    """Vercel entry point that preserves the original path through one function."""

    database = database

    def _restore_rewritten_path(self) -> None:
        parsed = urlparse(self.path)
        routed_path = parse_qs(parsed.query).get("path")
        if routed_path:
            self.path = f"/{routed_path[0].lstrip('/')}"
        elif parsed.path.rstrip("/") == "/api":
            self.path = "/"

    def do_GET(self) -> None:  # noqa: N802
        self._restore_rewritten_path()
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self._restore_rewritten_path()
        super().do_POST()

    def do_PUT(self) -> None:  # noqa: N802
        self._restore_rewritten_path()
        super().do_PUT()

    def do_DELETE(self) -> None:  # noqa: N802
        self._restore_rewritten_path()
        super().do_DELETE()
