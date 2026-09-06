from __future__ import annotations

import json
import ipaddress
import mimetypes
import re
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .config import (
    COOKIE_PARTITIONED,
    COOKIE_SAME_SITE,
    COOKIE_SECURE,
    FIREBASE_FRONTEND_ORIGINS,
    FIREBASE_PROJECT_ID,
    FRAME_ANCESTORS,
    IS_RENDER,
    IS_VERCEL,
    MAX_JSON_BYTES,
    MAX_MINUTES_PER_USER,
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    STATIC_DIR,
    ADMIN_EMAIL,
    ASESOR_EMAIL,
)
from .database import Database
from .document_engine import DocumentGenerationError, generate_docx
from .schema import load_schema, normalize_payload, validate_payload
from .security import safe_filename, verify_password


@dataclass
class LoginLimiter:
    attempts: dict[str, list[float]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    window_seconds: int = 5 * 60
    max_attempts: int = 8
    last_cleanup: float = 0

    def allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            if now - self.last_cleanup >= 60:
                for attempt_key, stamps in list(self.attempts.items()):
                    active = [stamp for stamp in stamps if now - stamp < self.window_seconds]
                    if active:
                        self.attempts[attempt_key] = active
                    else:
                        self.attempts.pop(attempt_key, None)
                self.last_cleanup = now
            recent = [
                stamp
                for stamp in self.attempts.get(key, [])
                if now - stamp < self.window_seconds
            ]
            if len(recent) >= self.max_attempts:
                self.attempts[key] = recent
                return False
            recent.append(now)
            self.attempts[key] = recent
            return True

    def reset(self, key: str) -> None:
        with self.lock:
            self.attempts.pop(key, None)


LOGIN_LIMITER = LoginLimiter()


def verify_firebase_id_token(token: str) -> dict[str, Any]:
    """Verify a Firebase ID token without granting the service database access."""
    if not FIREBASE_PROJECT_ID:
        raise RuntimeError("Firebase no está configurado para generar documentos.")
    import firebase_admin
    from firebase_admin import auth as firebase_auth

    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(options={"projectId": FIREBASE_PROJECT_ID})
    return firebase_auth.verify_id_token(token, check_revoked=False)


class VillaHermosaHandler(BaseHTTPRequestHandler):
    database = Database()
    server_version = "VillaHermosa/1.0"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, format: str, *args: Any) -> None:
        message = format % args
        print(f"[{self.log_date_time_string()}] {self.client_address[0]} {message}")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            self._api_get(path)
        else:
            self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/firebase/generate":
            self._firebase_generate()
            return
        self._api_mutation("POST", path)

    def do_PUT(self) -> None:  # noqa: N802
        self._api_mutation("PUT", urlparse(self.path).path)

    def do_DELETE(self) -> None:  # noqa: N802
        self._api_mutation("DELETE", urlparse(self.path).path)

    def do_OPTIONS(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        origin = self.headers.get("Origin", "")
        if path != "/api/firebase/generate" or origin not in FIREBASE_FRONTEND_ORIGINS:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        self._cors_origin = origin
        self.send_response(HTTPStatus.NO_CONTENT)
        self._security_headers()
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "3600")
        self.end_headers()

    def _firebase_generate(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin not in FIREBASE_FRONTEND_ORIGINS:
            self._json_error(HTTPStatus.FORBIDDEN, "Origen no autorizado.")
            return
        self._cors_origin = origin
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            self._json_error(HTTPStatus.UNAUTHORIZED, "Tu sesión de Firebase no está activa.")
            return
        token = authorization.removeprefix("Bearer ").strip()
        try:
            claims = verify_firebase_id_token(token)
        except Exception:
            self._json_error(HTTPStatus.UNAUTHORIZED, "No pudimos validar tu sesión de Firebase.")
            return
        email = str(claims.get("email", "")).strip().lower()
        if email not in {ADMIN_EMAIL, ASESOR_EMAIL}:
            self._json_error(HTTPStatus.FORBIDDEN, "Esta cuenta no tiene acceso a Minutas.")
            return
        body = self._read_json()
        if body is None:
            return
        raw_payload = body.get("payload")
        if not isinstance(raw_payload, dict):
            self._validation_error({"payload": "Envía un grupo de datos válido."})
            return
        payload = normalize_payload(raw_payload)
        errors = validate_payload(payload, for_generation=True)
        if errors:
            self._validation_error(errors, "Faltan datos para generar la minuta.")
            return
        try:
            document = generate_docx(payload)
        except DocumentGenerationError as error:
            self._json_error(HTTPStatus.UNPROCESSABLE_ENTITY, str(error))
            return
        buyers = payload.get("compradores", [])
        first_buyer = buyers[0] if isinstance(buyers, list) and buyers else {}
        client = safe_filename(
            first_buyer.get("nombre_completo", "") if isinstance(first_buyer, dict) else "",
            "cliente",
        )
        reference = safe_filename(str(body.get("reference", "minuta")), "minuta")
        self._bytes(
            document,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"{reference}-{client}.docx",
        )

    def _api_get(self, path: str) -> None:
        if path == "/api/health":
            self._json({"ok": True, "service": "Villa Hermosa Minutas"})
            return

        session = self._session()
        if not session:
            self._json_error(HTTPStatus.UNAUTHORIZED, "Tu sesión no está activa.")
            return

        if path == "/api/session":
            self._json({"user": self._public_user(session), "csrfToken": session["csrf_token"]})
            return
        if path == "/api/schema":
            schema = load_schema().copy()
            schema.pop("bindings", None)
            self._json(schema)
            return
        if path == "/api/minutes":
            items = self.database.list_minutes(session["id"], session["role"])
            self._json({"items": items})
            return
        if path == "/api/stats":
            stats = self.database.stats(session["id"], session["role"])
            self._json(stats)
            return
        if path == "/api/users":
            if session["role"] != "admin":
                self._json_error(HTTPStatus.FORBIDDEN, "Esta sección es solo para administración.")
                return
            self._json({"items": self.database.list_users()})
            return

        minute_match = re.fullmatch(r"/api/minutes/([0-9a-f-]{36})", path)
        if minute_match:
            item = self.database.get_minute(
                minute_match.group(1), session["id"], session["role"]
            )
            if not item:
                self._json_error(HTTPStatus.NOT_FOUND, "No encontramos esa minuta.")
                return
            self._json(item)
            return
        self._json_error(HTTPStatus.NOT_FOUND, "Ruta no encontrada.")

    def _api_mutation(self, method: str, path: str) -> None:
        if path == "/api/login" and method == "POST":
            self._login()
            return

        session = self._session()
        if not session:
            self._json_error(HTTPStatus.UNAUTHORIZED, "Tu sesión venció. Vuelve a ingresar.")
            return
        if not self._valid_csrf(session):
            self._json_error(HTTPStatus.FORBIDDEN, "No pudimos validar la solicitud.")
            return

        if path == "/api/logout" and method == "POST":
            token = self._session_token()
            if token:
                self.database.delete_session(token)
            self._clear_session_cookie()
            self._json({"ok": True})
            return

        if path == "/api/minutes" and method == "POST":
            if self.database.count_minutes_for_user(session["id"]) >= MAX_MINUTES_PER_USER:
                self._json_error(
                    HTTPStatus.CONFLICT,
                    "Alcanzaste el límite de expedientes. Contacta a administración.",
                )
                return
            body = self._read_json()
            if body is None:
                return
            raw_payload = body.get("payload")
            if not isinstance(raw_payload, dict):
                self._validation_error({"payload": "Envía un grupo de datos válido."})
                return
            payload = normalize_payload(raw_payload)
            errors = validate_payload(payload)
            if errors:
                self._validation_error(errors)
                return
            item = self.database.create_minute(session["id"], payload)
            self._json(item, HTTPStatus.CREATED)
            return

        minute_match = re.fullmatch(
            r"/api/minutes/([0-9a-f-]{36})(?:/(generate))?", path
        )
        if not minute_match:
            self._json_error(HTTPStatus.NOT_FOUND, "Ruta no encontrada.")
            return
        minute_id, action = minute_match.groups()

        if method == "PUT" and not action:
            body = self._read_json()
            if body is None:
                return
            raw_payload = body.get("payload")
            if not isinstance(raw_payload, dict):
                self._validation_error({"payload": "Envía un grupo de datos válido."})
                return
            payload = normalize_payload(raw_payload)
            errors = validate_payload(payload)
            if errors:
                self._validation_error(errors)
                return
            item = self.database.update_minute(
                minute_id, session["id"], session["role"], payload
            )
            if not item:
                self._json_error(HTTPStatus.NOT_FOUND, "No encontramos esa minuta.")
                return
            self._json(item)
            return

        if method == "DELETE" and not action:
            if session["role"] != "admin":
                self._json_error(
                    HTTPStatus.FORBIDDEN,
                    "Solo administración puede eliminar minutas.",
                )
                return
            existing = self.database.get_minute(
                minute_id, session["id"], session["role"]
            )
            if not existing or not self.database.delete_minute(minute_id, session["id"]):
                self._json_error(HTTPStatus.NOT_FOUND, "No encontramos esa minuta.")
                return
            self._json({}, HTTPStatus.NO_CONTENT)
            return

        if method == "POST" and action == "generate":
            item = self.database.get_minute(
                minute_id, session["id"], session["role"]
            )
            if not item:
                self._json_error(HTTPStatus.NOT_FOUND, "No encontramos esa minuta.")
                return
            errors = validate_payload(item["payload"], for_generation=True)
            if errors:
                self._validation_error(errors, "Faltan datos para generar la minuta.")
                return
            try:
                document = generate_docx(item["payload"])
            except DocumentGenerationError as error:
                self._json_error(HTTPStatus.UNPROCESSABLE_ENTITY, str(error))
                return
            self.database.mark_generated(minute_id, session["id"])
            client = safe_filename(item["client_name"], "cliente")
            filename = f"{item['reference']}-{client}.docx"
            self._bytes(
                document,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename,
            )
            return

        self._json_error(HTTPStatus.METHOD_NOT_ALLOWED, "Acción no permitida.")

    def _login(self) -> None:
        body = self._read_json()
        if body is None:
            return
        email = str(body.get("email", "")).strip().lower()
        ip_key = f"ip:{self._client_ip()}"
        account_key = f"account:{email}"
        if not self._login_attempt_allowed(ip_key) or not self._login_attempt_allowed(
            account_key
        ):
            self._json_error(
                HTTPStatus.TOO_MANY_REQUESTS,
                "Demasiados intentos. Espera unos minutos e inténtalo otra vez.",
            )
            return
        password = str(body.get("password", ""))
        user = self.database.get_user_by_email(email)
        if not user or not verify_password(
            password, user["password_salt"], user["password_hash"]
        ):
            self._json_error(HTTPStatus.UNAUTHORIZED, "Correo o contraseña incorrectos.")
            return
        self._reset_login_attempt(ip_key)
        self._reset_login_attempt(account_key)
        token, csrf = self.database.create_session(user["id"])
        self._set_session_cookie(token)
        self._json(
            {
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "display_name": user["display_name"],
                    "role": user["role"],
                },
                "csrfToken": csrf,
            }
        )

    def _client_ip(self) -> str:
        if IS_VERCEL:
            raw = self.headers.get("X-Vercel-Forwarded-For", "")
        elif IS_RENDER:
            # Render's public edge overwrites this header; X-Forwarded-For can
            # contain caller-supplied entries and must not key the limiter.
            values = self.headers.get_all("CF-Connecting-IP", [])
            raw = values[0] if len(values) == 1 else ""
        else:
            raw = self.client_address[0]
        try:
            return str(ipaddress.ip_address(raw.strip()))
        except ValueError:
            return str(self.client_address[0])

    def _login_attempt_allowed(self, key: str) -> bool:
        persistent = getattr(self.database, "allow_login_attempt", None)
        if callable(persistent):
            return bool(
                persistent(
                    key,
                    window_seconds=LOGIN_LIMITER.window_seconds,
                    max_attempts=LOGIN_LIMITER.max_attempts,
                )
            )
        return LOGIN_LIMITER.allowed(key)

    def _reset_login_attempt(self, key: str) -> None:
        persistent = getattr(self.database, "reset_login_attempt", None)
        if callable(persistent):
            persistent(key)
            return
        LOGIN_LIMITER.reset(key)

    def _session_token(self) -> str | None:
        raw_cookie = self.headers.get("Cookie")
        if not raw_cookie:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(raw_cookie)
        except Exception:
            return None
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel else None

    def _session(self) -> dict[str, Any] | None:
        token = self._session_token()
        return self.database.get_session(token) if token else None

    def _valid_csrf(self, session: dict[str, Any]) -> bool:
        supplied = self.headers.get("X-CSRF-Token", "")
        return bool(supplied) and supplied == session["csrf_token"]

    def _read_json(self) -> dict[str, Any] | None:
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            self._json_error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Se esperaba contenido JSON.")
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_JSON_BYTES:
            self._json_error(HTTPStatus.BAD_REQUEST, "La solicitud está vacía o es demasiado grande.")
            return None
        try:
            value = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json_error(HTTPStatus.BAD_REQUEST, "El contenido JSON no es válido.")
            return None
        if not isinstance(value, dict):
            self._json_error(HTTPStatus.BAD_REQUEST, "El contenido debe ser un objeto JSON.")
            return None
        return value

    def _serve_static(self, path: str) -> None:
        requested = unquote(path)
        if requested == "/":
            requested = "/index.html"
        candidate = (STATIC_DIR / requested.lstrip("/")).resolve()
        try:
            candidate.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            candidate = STATIC_DIR / "index.html"
        try:
            content = candidate.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self._flush_pending_cookie()
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") or content_type in {"application/javascript", "application/json", "image/svg+xml"} else content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache" if candidate.name == "index.html" else "public, max-age=3600")
        self.end_headers()
        self.wfile.write(content)

    def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        if status == HTTPStatus.NO_CONTENT:
            self.send_response(status)
            self._security_headers()
            self._flush_pending_cookie()
            self.end_headers()
            return
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self._flush_pending_cookie()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, value: bytes, content_type: str, filename: str) -> None:
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self._flush_pending_cookie()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(value)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(value)

    def _json_error(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, status)

    def _validation_error(
        self, errors: dict[str, str], message: str = "Revisa los datos ingresados."
    ) -> None:
        self._json(
            {"error": message, "fieldErrors": errors},
            HTTPStatus.UNPROCESSABLE_ENTITY,
        )

    def _security_headers(self) -> None:
        cors_origin = getattr(self, "_cors_origin", None)
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Access-Control-Expose-Headers", "Content-Disposition")
            self.send_header("Vary", "Origin")
        frame_ancestors = " ".join(FRAME_ANCESTORS) if FRAME_ANCESTORS else "'none'"
        self.send_header("X-Content-Type-Options", "nosniff")
        if not FRAME_ANCESTORS:
            self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if COOKIE_SECURE:
            self.send_header(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; "
            f"base-uri 'self'; frame-ancestors {frame_ancestors}",
        )

    def _set_session_cookie(self, token: str) -> None:
        parts = [
            f"{SESSION_COOKIE}={token}",
            "Path=/",
            "HttpOnly",
            f"SameSite={COOKIE_SAME_SITE}",
            f"Max-Age={SESSION_TTL_SECONDS}",
        ]
        if COOKIE_SECURE:
            parts.append("Secure")
        if COOKIE_PARTITIONED:
            parts.append("Partitioned")
        self._pending_cookie = "; ".join(parts)

    def _clear_session_cookie(self) -> None:
        parts = [
            f"{SESSION_COOKIE}=",
            "Path=/",
            "HttpOnly",
            f"SameSite={COOKIE_SAME_SITE}",
            "Max-Age=0",
        ]
        if COOKIE_SECURE:
            parts.append("Secure")
        if COOKIE_PARTITIONED:
            parts.append("Partitioned")
        self._pending_cookie = "; ".join(parts)

    def _flush_pending_cookie(self) -> None:
        value = getattr(self, "_pending_cookie", None)
        if value:
            self.send_header("Set-Cookie", value)
            self._pending_cookie = None

    @staticmethod
    def _public_user(session: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": session["id"],
            "email": session["email"],
            "display_name": session["display_name"],
            "role": session["role"],
            "last_login_at": session.get("last_login_at"),
        }
