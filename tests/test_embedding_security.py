from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
import unittest
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import crypt, jwt
from google.auth.exceptions import TransportError

from backend import config, http_app


class EmbeddingSecurityTest(unittest.TestCase):
    def signed_firebase_token(self, **overrides):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        now = datetime.now(timezone.utc)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")]))
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")]))
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .sign(key, hashes.SHA256())
        )
        claims = {
            "aud": "minutas-villa-hermosa",
            "iss": "https://securetoken.google.com/minutas-villa-hermosa",
            "sub": "test-user",
            "email": "asesor@villahermosa.com",
            "iat": int(time.time()) - 10,
            "exp": int(time.time()) + 3600,
            "auth_time": int(time.time()) - 10,
        }
        claims.update(overrides)
        token = jwt.encode(
            crypt.RSASigner.from_string(private_pem), claims, key_id="test-key"
        ).decode("ascii")
        certs = {"test-key": certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")}
        return token, certs

    def test_firebase_token_verification_requires_signature_audience_and_issuer(self):
        token, certs = self.signed_firebase_token()
        with patch.object(http_app, "FIREBASE_PROJECT_ID", "minutas-villa-hermosa"), patch(
            "google.oauth2.id_token._fetch_certs", return_value=certs
        ):
            self.assertEqual(http_app.verify_firebase_id_token(token)["sub"], "test-user")
            parts = token.split(".")
            parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
            with self.assertRaises(http_app.InvalidFirebaseToken):
                http_app.verify_firebase_id_token(".".join(parts))

        for bad_claims in (
            {"aud": "another-project"},
            {"iss": "https://securetoken.google.com/another-project"},
            {"sub": ""},
            {"auth_time": int(time.time()) + 3600},
        ):
            bad_token, bad_certs = self.signed_firebase_token(**bad_claims)
            with patch.object(http_app, "FIREBASE_PROJECT_ID", "minutas-villa-hermosa"), patch(
                "google.oauth2.id_token._fetch_certs", return_value=bad_certs
            ), self.assertRaises(http_app.InvalidFirebaseToken):
                http_app.verify_firebase_id_token(bad_token)

    def test_firebase_certificate_outage_is_not_reported_as_invalid_session(self):
        token, _ = self.signed_firebase_token()
        with patch.object(http_app, "FIREBASE_PROJECT_ID", "minutas-villa-hermosa"), patch(
            "google.oauth2.id_token._fetch_certs", side_effect=TransportError("offline")
        ), self.assertRaises(http_app.FirebaseVerificationUnavailable):
            http_app.verify_firebase_id_token(token)

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

    def test_firebase_document_endpoint_exposes_only_the_trusted_origin(self):
        trusted_origin = "https://minutas-villa-hermosa.web.app"
        handler = self.handler()
        handler._cors_origin = trusted_origin

        handler._security_headers()

        headers = dict(handler.sent_headers)
        self.assertEqual(headers["Access-Control-Allow-Origin"], trusted_origin)
        self.assertEqual(headers["Access-Control-Expose-Headers"], "Content-Disposition")
        self.assertEqual(headers["Vary"], "Origin")


if __name__ == "__main__":
    unittest.main()
