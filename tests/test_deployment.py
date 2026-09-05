from __future__ import annotations

import importlib
import os
import unittest
from unittest.mock import patch

from backend import config
import server


class DeploymentConfigTest(unittest.TestCase):
    def tearDown(self):
        importlib.reload(config)

    def test_local_defaults_are_preserved(self):
        with patch.dict(os.environ, {}, clear=True):
            importlib.reload(config)
            self.assertEqual(config.HOST, "127.0.0.1")
            self.assertEqual(config.PORT, 8000)
            self.assertFalse(config.COOKIE_SECURE)

    def test_cloud_defaults_bind_platform_port_and_secure_cookie(self):
        for provider in ({"K_SERVICE": "minutas"}, {"RENDER": "true"}):
            with self.subTest(provider=provider), patch.dict(
                os.environ, {**provider, "PORT": "10000", "VH_PORT": "8010"}, clear=True
            ):
                importlib.reload(config)
                self.assertEqual(config.HOST, "0.0.0.0")
                self.assertEqual(config.PORT, 10000)
                self.assertTrue(config.COOKIE_SECURE)
                self.assertEqual(config.SESSION_COOKIE, "__Host-vh_session")

    def test_hosted_service_refuses_ephemeral_sqlite(self):
        with patch.multiple(server, IS_HOSTED=True, DATABASE_URL="", HOST="127.0.0.1"):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                server.validate_runtime_security()

    def test_hosted_service_requires_secure_cookies_even_on_loopback(self):
        with patch.multiple(
            server, IS_HOSTED=True, DATABASE_URL="postgresql://example.invalid/db",
            HOST="127.0.0.1", COOKIE_SECURE=False
        ):
            with self.assertRaisesRegex(RuntimeError, "VH_COOKIE_SECURE"):
                server.validate_runtime_security()

    def test_postgres_selection_never_creates_local_storage(self):
        with patch.object(server, "DATABASE_URL", "postgresql://example.invalid/db"), \
             patch.object(server, "ensure_runtime_dirs") as make_dirs, \
             patch("backend.database_postgres.PostgresDatabase") as postgres:
            self.assertIs(server.create_database(), postgres.return_value)
            postgres.assert_called_once_with("postgresql://example.invalid/db")
            make_dirs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
