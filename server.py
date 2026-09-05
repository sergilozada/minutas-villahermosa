from __future__ import annotations

from http.server import ThreadingHTTPServer
from ipaddress import ip_address

from backend.config import (
    ADMIN_PASSWORD,
    ASESOR_PASSWORD,
    COOKIE_SECURE,
    DATABASE_URL,
    HOST,
    IS_HOSTED,
    PORT,
    ensure_runtime_dirs,
)
from backend.database import Database
from backend.http_app import VillaHermosaHandler


class VillaHermosaServer(ThreadingHTTPServer):
    daemon_threads = True


def _local_binding(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def validate_runtime_security() -> None:
    if IS_HOSTED and not DATABASE_URL:
        raise RuntimeError("El alojamiento web requiere DATABASE_URL; no se permite SQLite efímero.")
    if _local_binding(HOST) and not IS_HOSTED:
        return
    if not COOKIE_SECURE:
        raise RuntimeError(
            "Al publicar fuera de localhost debes activar VH_COOKIE_SECURE=1 y servir por HTTPS."
        )
    if ADMIN_PASSWORD is None or ASESOR_PASSWORD is None:
        raise RuntimeError(
            "Al publicar fuera de localhost debes definir VH_ADMIN_PASSWORD y VH_ASESOR_PASSWORD."
        )


def create_database():
    if DATABASE_URL:
        from backend.database_postgres import PostgresDatabase

        return PostgresDatabase(DATABASE_URL)
    ensure_runtime_dirs()
    return Database()


def main() -> None:
    validate_runtime_security()
    database = create_database()
    generated_credentials = database.initialize()
    VillaHermosaHandler.database = database
    server = VillaHermosaServer((HOST, PORT), VillaHermosaHandler)
    print(f"Villa Hermosa Minutas disponible en http://{HOST}:{PORT}")
    if generated_credentials and not IS_HOSTED:
        print("\nCredenciales creadas para este primer arranque:")
        for credential in generated_credentials:
            print(
                f"- {credential['role']}: {credential['email']} / "
                f"{credential['password']}"
            )
        print("Guárdalas ahora: no volverán a mostrarse.\n")
    print("Presiona Ctrl+C para detener el servidor.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
