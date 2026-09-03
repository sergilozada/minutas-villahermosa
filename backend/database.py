from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    ASESOR_EMAIL,
    ASESOR_PASSWORD,
    DATABASE_PATH,
    SESSION_TTL_SECONDS,
)
from .security import hash_password, new_token, token_hash
from .schema import normalize_payload


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path = DATABASE_PATH) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> list[dict[str, str]]:
        generated_credentials: list[dict[str, str]] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'asesor')),
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_login_at TEXT
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    csrf_token TEXT NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS minutes (
                    id TEXT PRIMARY KEY,
                    reference TEXT NOT NULL UNIQUE,
                    client_name TEXT NOT NULL,
                    document_number TEXT,
                    status TEXT NOT NULL DEFAULT 'borrador'
                        CHECK (status IN ('borrador', 'generada')),
                    payload_json TEXT NOT NULL,
                    created_by INTEGER NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    generated_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_minutes_created_by
                    ON minutes(created_by);
                CREATE INDEX IF NOT EXISTS idx_minutes_updated_at
                    ON minutes(updated_at DESC);

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER REFERENCES users(id),
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT,
                    created_at TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );
                """
            )
            admin_password = self._seed_user(
                connection,
                ADMIN_EMAIL,
                "Administrador Villa Hermosa",
                "admin",
                ADMIN_PASSWORD,
            )
            if admin_password:
                generated_credentials.append(
                    {"role": "Administrador", "email": ADMIN_EMAIL, "password": admin_password}
                )
            asesor_password = self._seed_user(
                connection,
                ASESOR_EMAIL,
                "Asesor Villa Hermosa",
                "asesor",
                ASESOR_PASSWORD,
            )
            if asesor_password:
                generated_credentials.append(
                    {"role": "Asesor", "email": ASESOR_EMAIL, "password": asesor_password}
                )
            self._prune_sessions(connection)
        return generated_credentials

    @staticmethod
    def _seed_user(
        connection: sqlite3.Connection,
        email: str,
        display_name: str,
        role: str,
        password: str | None,
    ) -> str | None:
        exists = connection.execute(
            "SELECT 1 FROM users WHERE email = ?", (email,)
        ).fetchone()
        if exists:
            return None
        generated_password = password is None
        initial_password = password or new_token(18)
        salt, digest = hash_password(initial_password)
        connection.execute(
            """
            INSERT INTO users (
                email, display_name, role, password_salt, password_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (email, display_name, role, salt, digest, utc_now()),
        )
        return initial_password if generated_password else None

    @staticmethod
    def _prune_sessions(connection: sqlite3.Connection) -> None:
        connection.execute(
            "DELETE FROM sessions WHERE expires_at <= ?", (utc_now(),)
        )

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ? AND active = 1", (email,)
            ).fetchone()
        return dict(row) if row else None

    def create_session(self, user_id: int) -> tuple[str, str]:
        token = new_token(36)
        csrf = new_token(24)
        expires = datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS)
        with self.connect() as connection:
            self._prune_sessions(connection)
            connection.execute(
                """
                INSERT INTO sessions (token_hash, csrf_token, user_id, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token_hash(token), csrf, user_id, expires.isoformat(), utc_now()),
            )
            connection.execute(
                "UPDATE users SET last_login_at = ? WHERE id = ?", (utc_now(), user_id)
            )
        return token, csrf

    def get_session(self, token: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT s.csrf_token, s.expires_at,
                       u.id, u.email, u.display_name, u.role, u.last_login_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1
                """,
                (token_hash(token), utc_now()),
            ).fetchone()
        return dict(row) if row else None

    def delete_session(self, token: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),)
            )

    def list_users(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, email, display_name, role, active, created_at, last_login_at
                FROM users ORDER BY role, display_name
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def count_minutes_for_user(self, user_id: int) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM minutes WHERE created_by = ?", (user_id,)
            ).fetchone()
        return int(row["total"] or 0)

    @staticmethod
    def _reference_for(connection: sqlite3.Connection) -> str:
        prefix = datetime.now(timezone.utc).strftime("VH-%Y%m")
        row = connection.execute(
            """
            SELECT COALESCE(MAX(CAST(substr(reference, ?) AS INTEGER)), 0) AS last
            FROM minutes WHERE reference LIKE ?
            """,
            (len(prefix) + 2, f"{prefix}-%"),
        ).fetchone()
        return f"{prefix}-{int(row['last']) + 1:04d}"

    def create_minute(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        payload = normalize_payload(payload)
        minute_id = str(uuid.uuid4())
        now = utc_now()
        client_name, document_number = self._buyer_identity(payload)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            reference = self._reference_for(connection)
            connection.execute(
                """
                INSERT INTO minutes (
                    id, reference, client_name, document_number, payload_json,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    minute_id,
                    reference,
                    client_name,
                    document_number,
                    json.dumps(payload, ensure_ascii=False),
                    user_id,
                    now,
                    now,
                ),
            )
            self._audit(connection, user_id, "crear", "minuta", minute_id)
        return self.get_minute(minute_id, user_id, "admin")  # creator always has access

    def get_minute(
        self, minute_id: str, user_id: int, role: str
    ) -> dict[str, Any] | None:
        where = "m.id = ?"
        params: list[Any] = [minute_id]
        if role != "admin":
            where += " AND m.created_by = ?"
            params.append(user_id)
        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT m.*, u.display_name AS owner_name, u.email AS owner_email
                FROM minutes m JOIN users u ON u.id = m.created_by
                WHERE {where}
                """,
                params,
            ).fetchone()
        return self._minute_row(row) if row else None

    def list_minutes(self, user_id: int, role: str) -> list[dict[str, Any]]:
        where = "" if role == "admin" else "WHERE m.created_by = ?"
        params: tuple[Any, ...] = () if role == "admin" else (user_id,)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT m.*, u.display_name AS owner_name, u.email AS owner_email
                FROM minutes m JOIN users u ON u.id = m.created_by
                {where}
                ORDER BY m.updated_at DESC
                """,
                params,
            ).fetchall()
        return [self._minute_row(row) for row in rows]

    def update_minute(
        self,
        minute_id: str,
        user_id: int,
        role: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        payload = normalize_payload(payload)
        existing = self.get_minute(minute_id, user_id, role)
        if not existing:
            return None
        now = utc_now()
        client_name, document_number = self._buyer_identity(payload)
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE minutes
                SET client_name = ?, document_number = ?, payload_json = ?,
                    updated_at = ?, status = 'borrador'
                WHERE id = ?
                """,
                (
                    client_name,
                    document_number,
                    json.dumps(payload, ensure_ascii=False),
                    now,
                    minute_id,
                ),
            )
            self._audit(connection, user_id, "editar", "minuta", minute_id)
        return self.get_minute(minute_id, user_id, role)

    def mark_generated(self, minute_id: str, user_id: int) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE minutes SET status = 'generada', generated_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, minute_id),
            )
            self._audit(connection, user_id, "generar", "minuta", minute_id)

    def delete_minute(self, minute_id: str, user_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM minutes WHERE id = ?", (minute_id,))
            if cursor.rowcount:
                self._audit(connection, user_id, "eliminar", "minuta", minute_id)
        return bool(cursor.rowcount)

    def stats(self, user_id: int, role: str) -> dict[str, int]:
        where = "" if role == "admin" else "WHERE created_by = ?"
        params: tuple[Any, ...] = () if role == "admin" else (user_id,)
        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status = 'borrador' THEN 1 ELSE 0 END) AS borradores,
                       SUM(CASE WHEN status = 'generada' THEN 1 ELSE 0 END) AS generadas
                FROM minutes {where}
                """,
                params,
            ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "borradores": int(row["borradores"] or 0),
            "generadas": int(row["generadas"] or 0),
        }

    @staticmethod
    def _minute_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["payload"] = normalize_payload(json.loads(item.pop("payload_json")))
        item["client_name"], item["document_number"] = Database._buyer_identity(
            item["payload"]
        )
        return item

    @staticmethod
    def _buyer_identity(payload: dict[str, Any]) -> tuple[str, str]:
        buyers = payload.get("compradores", [])
        if not isinstance(buyers, list):
            return "", ""
        names = [
            str(item.get("nombre_completo", "")).strip()
            for item in buyers
            if isinstance(item, dict) and str(item.get("nombre_completo", "")).strip()
        ]
        documents = [
            str(item.get("documento", "")).strip()
            for item in buyers
            if isinstance(item, dict) and str(item.get("documento", "")).strip()
        ]
        return " · ".join(names), " · ".join(documents)

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        user_id: int,
        action: str,
        entity_type: str,
        entity_id: str | None,
        details: dict[str, Any] | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_log (
                user_id, action, entity_type, entity_id, created_at, details_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                action,
                entity_type,
                entity_id,
                utc_now(),
                json.dumps(details or {}, ensure_ascii=False),
            ),
        )
