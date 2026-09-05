from __future__ import annotations

import unittest
from unittest.mock import patch

from backend import config, http_app


class EmbeddingSecurityTest(unittest.TestCase):
    def handler(self):
        instance = object.__new__(http_app.VillaHermosaHandler)
        instance.sent_headers = []
        instance.send_header = lambda name, value: instance.sent_headers.append((name, value))
        return instance

    def test_frame_origin_parser_accepts_only_exact_https_origins(self):
        self.assertEqual(
            config._parse_frame_ancestors(
                "https://condominio-villa-hermosa.web.app/ "
                "http://inseguro.example https://usuario@evil.example "
                "https://example.com/ruta https://example.com'"
            ),
            ("https://condominio-villa-hermosa.web.app",),
        )

    def test_default_headers_deny_all_framing(self):
        handler = self.handler()
        with patch.multiple(
            http_app,
            FRAME_ANCESTORS=(),
            COOKIE_SECURE=False,
        ):
            handler._security_headers()

        headers = dict(handler.sent_headers)
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_hosted_embed_allows_only_dashboard_and_uses_partitioned_cookie(self):
        trusted_origin = "https://condominio-villa-hermosa.web.app"
        handler = self.handler()
        with patch.multiple(
            http_app,
            FRAME_ANCESTORS=(trusted_origin,),
            COOKIE_SECURE=True,
            COOKIE_SAME_SITE="None",
            COOKIE_PARTITIONED=True,
        ):
            handler._security_headers()
            handler._set_session_cookie("token-seguro")

        headers = dict(handler.sent_headers)
        self.assertNotIn("X-Frame-Options", headers)
        self.assertIn(
            f"frame-ancestors {trusted_origin}", headers["Content-Security-Policy"]
        )
        self.assertEqual(
            handler._pending_cookie,
            f"{http_app.SESSION_COOKIE}=token-seguro; Path=/; HttpOnly; "
            f"SameSite=None; Max-Age={http_app.SESSION_TTL_SECONDS}; Secure; Partitioned",
        )


if __name__ == "__main__":
    unittest.main()
