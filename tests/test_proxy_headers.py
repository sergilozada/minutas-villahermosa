from __future__ import annotations

import unittest
from http.client import HTTPMessage
from unittest.mock import patch

from backend import http_app


class ProxyHeadersTest(unittest.TestCase):
    def client_ip(self, headers=(), *, render=False, vercel=False):
        # Exercise header selection without opening sockets or touching a DB.
        handler = object.__new__(http_app.VillaHermosaHandler)
        handler.client_address = ("192.0.2.10", 12345)
        handler.headers = HTTPMessage()
        for name, value in headers:
            handler.headers[name] = value
        with patch.multiple(http_app, IS_RENDER=render, IS_VERCEL=vercel):
            return handler._client_ip()

    def test_render_uses_one_valid_cloudflare_ip(self):
        for supplied, expected in (
            ("203.0.113.7", "203.0.113.7"),
            (" 2001:0db8::7 ", "2001:db8::7"),
        ):
            with self.subTest(supplied=supplied):
                self.assertEqual(
                    self.client_ip([("CF-Connecting-IP", supplied)], render=True),
                    expected,
                )

    def test_render_missing_invalid_or_multiple_ips_fall_back_to_peer(self):
        for headers in (
            [],
            [("CF-Connecting-IP", "")],
            [("CF-Connecting-IP", "not-an-ip")],
            [("CF-Connecting-IP", "203.0.113.7, 203.0.113.8")],
            [("CF-Connecting-IP", "203.0.113.7:443")],
            [("CF-Connecting-IP", "203.0.113.7"),
             ("CF-Connecting-IP", "203.0.113.8")],
        ):
            with self.subTest(headers=headers):
                self.assertEqual(self.client_ip(headers, render=True), "192.0.2.10")

    def test_render_ignores_untrusted_forwarded_headers(self):
        self.assertEqual(
            self.client_ip(
                [("X-Forwarded-For", "203.0.113.7"),
                 ("X-Vercel-Forwarded-For", "203.0.113.8")],
                render=True,
            ),
            "192.0.2.10",
        )

    def test_local_ignores_all_proxy_headers(self):
        self.assertEqual(
            self.client_ip(
                [("CF-Connecting-IP", "203.0.113.7"),
                 ("X-Vercel-Forwarded-For", "203.0.113.8"),
                 ("X-Forwarded-For", "203.0.113.9")]
            ),
            "192.0.2.10",
        )

    def test_vercel_behavior_is_preserved(self):
        self.assertEqual(
            self.client_ip(
                [("X-Vercel-Forwarded-For", "203.0.113.8"),
                 ("CF-Connecting-IP", "203.0.113.7")],
                vercel=True,
            ),
            "203.0.113.8",
        )
        for headers in ([], [("X-Vercel-Forwarded-For", "invalid")]):
            with self.subTest(headers=headers):
                self.assertEqual(self.client_ip(headers, vercel=True), "192.0.2.10")


if __name__ == "__main__":
    unittest.main()
