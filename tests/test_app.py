from __future__ import annotations

import copy
import io
import json
import re
import threading
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from xml.etree import ElementTree

from backend.database import Database
from backend.document_engine import generate_docx
from backend.http_app import LOGIN_LIMITER, VillaHermosaHandler
from backend.schema import normalize_payload, validate_payload
from backend.security import verify_password


def representative_payload() -> dict[str, Any]:
    return {
        "compradores": [
            {
                "nombre_completo": "Ana Lucía Mendoza Rojas",
                "documento": "72845136",
                "genero": "femenino",
                "nacionalidad": "Peruana",
                "ocupacion": "Arquitecta",
                "estado_civil": "soltera",
                "email": "ana.mendoza@example.com",
                "telefono": "987654321",
                "domicilio": "Av. Los Jardines 245",
                "distrito": "Santiago",
                "provincia": "Ica",
                "departamento": "Ica",
            },
            {
                "nombre_completo": "Bruno Esteban Torres Paz",
                "documento": "70123456",
                "genero": "masculino",
                "nacionalidad": "Peruana",
                "ocupacion": "Ingeniero civil",
                "estado_civil": "soltero",
                "email": "bruno.torres@example.com",
                "telefono": "986111222",
                "domicilio": "Calle Los Sauces 180",
                "distrito": "Ica",
                "provincia": "Ica",
                "departamento": "Ica",
            },
        ],
        "lote": "12",
        "manzana": "B",
        "area_m2": 120.5,
        "precio_total": 48000,
        "cuota_inicial": 12000,
        "pagos_iniciales": [
            {
                "metodo": "transferencia_bancaria",
                "monto": 12000,
                "numero_operacion": "OP-847392",
                "fecha_pago": "2026-08-20",
            }
        ],
        "pago_inicial_confirmado": True,
        "fecha_firma": "2026-08-24",
        "numero_cuotas_total": 12,
        "monto_cuota_regular": 3000,
        "fecha_primera_cuota": "2026-09-20",
        "revision_confirmada": True,
    }


def legacy_payload() -> dict[str, Any]:
    canonical = representative_payload()
    first = canonical["compradores"][0]
    payment = canonical["pagos_iniciales"][0]
    legacy = {
        **{
            key: value
            for key, value in canonical.items()
            if key not in {"compradores", "pagos_iniciales"}
        },
        **{f"comprador_{key}": value for key, value in first.items()},
        "fecha_pago_inicial": payment["fecha_pago"],
        "numero_operacion": payment["numero_operacion"],
    }
    legacy.pop("numero_cuotas_total")
    legacy["numero_cuotas_regulares"] = 11
    return legacy


class SchemaAndDocumentTest(unittest.TestCase):
    def test_canonical_legacy_validation_and_installment_semantics(self) -> None:
        canonical = normalize_payload(representative_payload())
        self.assertEqual(len(canonical["compradores"]), 2)
        self.assertEqual(canonical["numero_cuotas_total"], 12)
        self.assertEqual(canonical["numero_cuotas_regulares"], 11)
        self.assertEqual(canonical["monto_cuota_final"], 3000)
        self.assertEqual(canonical["total_pagos_iniciales"], 12000)
        self.assertEqual(validate_payload(canonical, for_generation=True), {})

        legacy = normalize_payload(legacy_payload())
        self.assertEqual(len(legacy["compradores"]), 1)
        self.assertEqual(legacy["compradores"][0]["documento"], "72845136")
        self.assertEqual(legacy["numero_cuotas_total"], 12)
        self.assertEqual(legacy["numero_cuotas_regulares"], 11)
        self.assertEqual(legacy["pagos_iniciales"][0]["metodo"], "transferencia_bancaria")
        self.assertEqual(legacy["pagos_iniciales"][0]["monto"], 12000)

        eighty_three = copy.deepcopy(representative_payload())
        eighty_three.update(
            {
                "precio_total": 100_000,
                "cuota_inicial": 0,
                "numero_cuotas_total": 83,
                "monto_cuota_regular": 1000,
            }
        )
        computed = normalize_payload(eighty_three)
        self.assertEqual(computed["numero_cuotas_regulares"], 82)
        self.assertEqual(computed["monto_cuota_final"], 18_000)

        automatic = copy.deepcopy(eighty_three)
        automatic["monto_cuota_regular"] = ""
        computed = normalize_payload(automatic)
        self.assertEqual(computed["monto_cuota_regular"], 1204.82)
        self.assertEqual(computed["monto_cuota_final"], 1204.76)

        remainder = copy.deepcopy(representative_payload())
        remainder.update(
            {
                "precio_total": 110,
                "cuota_inicial": 10,
                "pagos_iniciales": [
                    {
                        "metodo": "yape",
                        "monto": 10,
                        "numero_operacion": "YAPE-10",
                        "fecha_pago": "2026-08-20",
                    }
                ],
                "numero_cuotas_total": 3,
                "monto_cuota_regular": "",
            }
        )
        computed = normalize_payload(remainder)
        self.assertEqual(computed["monto_cuota_regular"], 33.33)
        self.assertEqual(computed["monto_cuota_final"], 33.34)
        self.assertEqual(validate_payload(computed, for_generation=True), {})

        multiple_payments = copy.deepcopy(representative_payload())
        multiple_payments["cuota_inicial"] = 2000
        multiple_payments["pagos_iniciales"] = [
            {
                "metodo": method,
                "monto": 500,
                "numero_operacion": f"OP-{index + 1}",
                "fecha_pago": f"2026-08-{20 + index:02d}",
            }
            for index, method in enumerate(
                ("yape", "plin", "deposito_cuenta", "transferencia_bancaria")
            )
        ]
        computed = normalize_payload(multiple_payments)
        self.assertEqual(computed["total_pagos_iniciales"], 2000)
        self.assertEqual(validate_payload(computed, for_generation=True), {})

        mismatch = copy.deepcopy(multiple_payments)
        mismatch["pagos_iniciales"][-1]["monto"] = 499.99
        errors = validate_payload(normalize_payload(mismatch), for_generation=True)
        self.assertIn("pagos_iniciales", errors)

        duplicate = copy.deepcopy(representative_payload())
        duplicate["compradores"][1]["documento"] = duplicate["compradores"][0]["documento"]
        errors = validate_payload(normalize_payload(duplicate), for_generation=True)
        self.assertIn("compradores.1.documento", errors)

        invalid_item = copy.deepcopy(representative_payload())
        invalid_item["compradores"] = [123]
        errors = validate_payload(normalize_payload(invalid_item), for_generation=True)
        self.assertIn("compradores.0", errors)

        too_many = copy.deepcopy(representative_payload())
        too_many["compradores"] = [
            {**too_many["compradores"][0], "documento": f"{index:08d}"}
            for index in range(11)
        ]
        errors = validate_payload(normalize_payload(too_many), for_generation=True)
        self.assertIn("compradores", errors)

        false_string = copy.deepcopy(representative_payload())
        false_string["pago_inicial_confirmado"] = "false"
        errors = validate_payload(normalize_payload(false_string), for_generation=True)
        self.assertIn("pago_inicial_confirmado", errors)

        boolean_total = copy.deepcopy(representative_payload())
        boolean_total["numero_cuotas_total"] = True
        errors = validate_payload(normalize_payload(boolean_total), for_generation=True)
        self.assertIn("numero_cuotas_total", errors)

        extreme_date = copy.deepcopy(representative_payload())
        extreme_date["fecha_primera_cuota"] = "9999-12-31"
        errors = validate_payload(normalize_payload(extreme_date), for_generation=True)
        self.assertIn("fecha_primera_cuota", errors)

    def test_document_contains_buyers_signatures_and_monthly_schedule(self) -> None:
        payload = copy.deepcopy(representative_payload())
        payload.update(
            {
                "precio_total": 3300,
                "cuota_inicial": 300,
                "pagos_iniciales": [
                    {
                        "metodo": "transferencia_bancaria",
                        "monto": 300,
                        "numero_operacion": "OP-300",
                        "fecha_pago": "2026-08-20",
                    }
                ],
                "numero_cuotas_total": 3,
                "monto_cuota_regular": 900,
                "fecha_primera_cuota": "2027-01-31",
            }
        )
        normalized = normalize_payload(payload)
        self.assertEqual(validate_payload(normalized, for_generation=True), {})
        document = generate_docx(normalized)
        with zipfile.ZipFile(io.BytesIO(document)) as generated:
            root = ElementTree.fromstring(generated.read("word/document.xml"))
            namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            tables = root.findall(".//w:tbl", namespace)
            schedule = next(
                table
                for table in tables
                if "Vencimiento" in "".join(
                    node.text or "" for node in table.findall(".//w:t", namespace)
                )
            )
            self.assertEqual(len(schedule.findall("./w:tr", namespace)), 4)
            schedule_text = " ".join(
                node.text or "" for node in schedule.findall(".//w:t", namespace)
            )
            self.assertIn("31/01/2027", schedule_text)
            self.assertIn("28/02/2027", schedule_text)
            self.assertIn("31/03/2027", schedule_text)
            full_text = " ".join(
                node.text or "" for node in root.findall(".//w:t", namespace)
            )
            self.assertIn("ANA LUCÍA MENDOZA ROJAS", full_text)
            self.assertIn("BRUNO ESTEBAN TORRES PAZ", full_text)
            self.assertGreaterEqual(full_text.count("EL COMPRADOR"), 3)
            self.assertNotIn("FIRMAS", full_text)

            body = root.find("./w:body", namespace)
            self.assertIsNotNone(body)
            body_paragraphs = body.findall("./w:p", namespace)
            body_paragraph_texts = [
                "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace))
                for paragraph in body_paragraphs
            ]
            first_buyer = "ANA LUCÍA MENDOZA ROJAS"
            second_buyer = "BRUNO ESTEBAN TORRES PAZ"
            buyer_intro_indexes = [
                index
                for index, text in enumerate(body_paragraph_texts)
                if first_buyer in text and second_buyer in text
            ]
            self.assertEqual(buyer_intro_indexes, [5])
            buyer_intro_index = buyer_intro_indexes[0]
            buyer_intro = body_paragraph_texts[buyer_intro_index]
            self.assertEqual(buyer_intro.count("□"), 1)
            self.assertNotIn("•", buyer_intro)
            self.assertNotIn("", buyer_intro)
            buyer_marker_run = next(
                run
                for run in body_paragraphs[buyer_intro_index].findall("./w:r", namespace)
                if "".join(node.text or "" for node in run.findall("./w:t", namespace))
                == "□ "
            )
            marker_fonts = buyer_marker_run.find("./w:rPr/w:rFonts", namespace)
            self.assertIsNotNone(marker_fonts)
            for font_attribute in ("ascii", "hAnsi", "cs"):
                self.assertEqual(
                    marker_fonts.get(f"{{{namespace['w']}}}{font_attribute}"),
                    "Segoe UI Symbol",
                )
            self.assertIn(f" y {second_buyer}", buyer_intro)
            self.assertNotIn(f". y {second_buyer}", buyer_intro)
            self.assertLess(buyer_intro.index(first_buyer), buyer_intro.index(second_buyer))
            self.assertIn(
                " a quienes en adelante se les denominará LOS COMPRADORES. ========",
                buyer_intro,
            )
            self.assertTrue(
                body_paragraph_texts[buyer_intro_index - 1].startswith("LOS COMPRADORES:")
            )
            self.assertFalse(
                any(text.startswith("EL COMPRADOR:") for text in body_paragraph_texts)
            )

            signature = next(
                table
                for table in tables
                if "EL VENDEDOR" in "".join(
                    node.text or "" for node in table.findall(".//w:t", namespace)
                )
                and "EL COMPRADOR" in "".join(
                    node.text or "" for node in table.findall(".//w:t", namespace)
                )
            )
            signature_text = " ".join(
                node.text or "" for node in signature.findall(".//w:t", namespace)
            )
            self.assertNotIn("EMPRESA INMOBILIARIA", signature_text)
            for buyer in normalized["compradores"]:
                name = buyer["nombre_completo"].upper()
                dni = f"DNI {buyer['documento']}"
                cell = next(
                    item
                    for item in signature.findall(".//w:tc", namespace)
                    if name in "".join(
                        node.text or "" for node in item.findall(".//w:t", namespace)
                    )
                )
                cell_text = " ".join(
                    node.text or "" for node in cell.findall(".//w:t", namespace)
                )
                self.assertLess(cell_text.index("EL COMPRADOR"), cell_text.index(name))
                self.assertLess(cell_text.index(name), cell_text.index(dni))
                name_run = next(
                    run
                    for run in cell.findall(".//w:r", namespace)
                    if "".join(node.text or "" for node in run.findall("./w:t", namespace)) == name
                )
                dni_run = next(
                    run
                    for run in cell.findall(".//w:r", namespace)
                    if "".join(node.text or "" for node in run.findall("./w:t", namespace)) == dni
                )
                self.assertIsNotNone(name_run.find("./w:rPr/w:b", namespace))
                self.assertIsNone(dni_run.find("./w:rPr/w:b", namespace))

            section = root.findall(".//w:sectPr", namespace)[-1]
            page_size = section.find("./w:pgSz", namespace)
            page_margin = section.find("./w:pgMar", namespace)
            self.assertEqual(page_size.get(f"{{{namespace['w']}}}w"), "11906")
            self.assertEqual(page_size.get(f"{{{namespace['w']}}}h"), "16838")
            self.assertIsNone(page_size.get(f"{{{namespace['w']}}}orient"))
            grid_width = sum(
                int(item.get(f"{{{namespace['w']}}}w"))
                for item in schedule.findall("./w:tblGrid/w:gridCol", namespace)
            )
            left = int(page_margin.get(f"{{{namespace['w']}}}left"))
            right = int(page_margin.get(f"{{{namespace['w']}}}right"))
            self.assertLessEqual(grid_width + 120, 11906 - left - right)

    def test_digital_initial_payments_omit_bank_account_from_clause(self) -> None:
        payload = copy.deepcopy(representative_payload())
        payload.update(
            {
                "precio_total": 5000,
                "cuota_inicial": 2000,
                "pagos_iniciales": [
                    {
                        "metodo": "yape" if index % 2 == 0 else "plin",
                        "monto": 500,
                        "numero_operacion": f"DIGITAL-{index + 1}",
                        "fecha_pago": f"2026-08-{20 + index:02d}",
                    }
                    for index in range(4)
                ],
                "numero_cuotas_total": 3,
                "monto_cuota_regular": 1000,
            }
        )
        normalized = normalize_payload(payload)
        self.assertEqual(validate_payload(normalized, for_generation=True), {})
        document = generate_docx(normalized)
        with zipfile.ZipFile(io.BytesIO(document)) as generated:
            root = ElementTree.fromstring(generated.read("word/document.xml"))
            namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            full_text = " ".join(
                node.text or "" for node in root.findall(".//w:t", namespace)
            )
            start = full_text.index("3.2.1")
            end = full_text.index("El saldo de", start)
            clause = full_text[start:end]
            self.assertIn("mediante Yape", clause)
            self.assertIn("mediante Plin", clause)
            for index in range(4):
                self.assertIn(f"DIGITAL-{index + 1}", clause)
            self.assertNotIn("4003008478638", clause)
            self.assertNotIn("Banco Interbank", clause)

    def test_transfer_accounts_and_initial_payments_are_continuous_and_chronological(self) -> None:
        payload = copy.deepcopy(representative_payload())
        payload.update(
            {
                "precio_total": 5000,
                "cuota_inicial": 1000,
                "pagos_iniciales": [
                    {
                        "metodo": "yape",
                        "monto": 200,
                        "numero_operacion": "YAPE-200",
                        "fecha_pago": "2026-08-22",
                    },
                    {
                        "metodo": "transferencia_bancaria",
                        "monto": 500,
                        "numero_operacion": "TB-500",
                        "fecha_pago": "2026-08-20",
                    },
                    {
                        "metodo": "transferencia_interbancaria",
                        "monto": 300,
                        "numero_operacion": "IB-300",
                        "fecha_pago": "2026-08-21",
                    },
                ],
                "numero_cuotas_total": 3,
                "monto_cuota_regular": 1500,
            }
        )
        normalized = normalize_payload(payload)
        self.assertEqual(validate_payload(normalized, for_generation=True), {})
        document = generate_docx(normalized)
        with zipfile.ZipFile(io.BytesIO(document)) as generated:
            root = ElementTree.fromstring(generated.read("word/document.xml"))
            namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            clause = next(
                "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace))
                for paragraph in root.findall(".//w:p", namespace)
                if "3.2.1" in "".join(
                    node.text or "" for node in paragraph.findall(".//w:t", namespace)
                )
            )

            for operation in ("TB-500", "IB-300", "YAPE-200"):
                self.assertIn(operation, clause)
            self.assertNotRegex(clause, r"\((?:i|ii|iii|iv)\)")
            self.assertNotIn(";", clause)
            self.assertIn("20 de agosto de 2026, S/ 300.00", clause)
            self.assertIn("21 de agosto de 2026 y S/ 200.00", clause)

            bank_start = clause.index("S/ 500.00")
            interbank_start = clause.index("S/ 300.00")
            yape_start = clause.index("S/ 200.00")
            self.assertLess(bank_start, interbank_start)
            self.assertLess(interbank_start, yape_start)
            bank_segment = clause[bank_start:interbank_start]
            interbank_segment = clause[interbank_start:yape_start]
            self.assertIn("4003008478638", bank_segment)
            self.assertNotIn("00340000300847863890", bank_segment)
            self.assertNotIn("CCI", bank_segment)
            self.assertIn("00340000300847863890", interbank_segment)
            self.assertNotIn("4003008478638", interbank_segment)
            self.assertNotIn("CCI", interbank_segment)

    def test_initial_payment_date_sort_is_stable_and_does_not_mutate_payload(self) -> None:
        payload = copy.deepcopy(representative_payload())
        payload.update(
            {
                "precio_total": 5000,
                "cuota_inicial": 1000,
                "pagos_iniciales": [
                    {
                        "metodo": "yape",
                        "monto": 250,
                        "numero_operacion": "LATEST",
                        "fecha_pago": "2026-08-22",
                    },
                    {
                        "metodo": "yape",
                        "monto": 250,
                        "numero_operacion": "SAME-A",
                        "fecha_pago": "2026-08-20",
                    },
                    {
                        "metodo": "yape",
                        "monto": 250,
                        "numero_operacion": "EARLIEST",
                        "fecha_pago": "2026-08-19",
                    },
                    {
                        "metodo": "yape",
                        "monto": 250,
                        "numero_operacion": "SAME-B",
                        "fecha_pago": "2026-08-20",
                    },
                ],
                "numero_cuotas_total": 3,
                "monto_cuota_regular": 1500,
            }
        )
        normalized = normalize_payload(payload)
        self.assertEqual(validate_payload(normalized, for_generation=True), {})
        input_order = [item["numero_operacion"] for item in normalized["pagos_iniciales"]]
        document = generate_docx(normalized)
        self.assertEqual(
            [item["numero_operacion"] for item in normalized["pagos_iniciales"]],
            input_order,
        )

        with zipfile.ZipFile(io.BytesIO(document)) as generated:
            root = ElementTree.fromstring(generated.read("word/document.xml"))
            namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            clause = next(
                "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace))
                for paragraph in root.findall(".//w:p", namespace)
                if "3.2.1" in "".join(
                    node.text or "" for node in paragraph.findall(".//w:t", namespace)
                )
            )
        positions = [
            clause.index(operation)
            for operation in ("EARLIEST", "SAME-A", "SAME-B", "LATEST")
        ]
        self.assertEqual(positions, sorted(positions))


class ApplicationSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = TemporaryDirectory()
        database = Database(Path(cls.temp_dir.name) / "test.db")
        cls.database = database
        credentials = database.initialize()
        cls.credentials = {item["role"]: item for item in credentials}

        for item in credentials:
            user = database.get_user_by_email(item["email"])
            assert user is not None
            assert verify_password(
                item["password"], user["password_salt"], user["password_hash"]
            )
        assert database.initialize() == []

        handler = type(
            "QuietTestHandler",
            (VillaHermosaHandler,),
            {"database": database, "log_message": lambda *args: None},
        )
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temp_dir.cleanup()

    def request(
        self,
        opener: Any,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        csrf: str | None = None,
    ) -> tuple[int, Any, dict[str, str]]:
        data = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if csrf:
            headers["X-CSRF-Token"] = csrf
        request = Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            response = opener.open(request, timeout=5)
        except HTTPError as error:
            response = error
        body = response.read()
        content_type = response.headers.get("Content-Type", "")
        parsed: Any = body
        if "application/json" in content_type and body:
            parsed = json.loads(body.decode("utf-8"))
        return response.status, parsed, dict(response.headers.items())

    def login(self, role: str) -> tuple[Any, str]:
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        credential = self.credentials[role]
        LOGIN_LIMITER.reset("ip:127.0.0.1")
        LOGIN_LIMITER.reset(f"account:{credential['email']}")
        status, body, _ = self.request(
            opener,
            "POST",
            "/api/login",
            {"email": credential["email"], "password": credential["password"]},
        )
        self.assertEqual(status, 200)
        return opener, body["csrfToken"]

    def test_roles_csrf_validation_and_docx_generation(self) -> None:
        admin, admin_csrf = self.login("Administrador")
        advisor, advisor_csrf = self.login("Asesor")

        status, admin_minute, _ = self.request(
            admin,
            "POST",
            "/api/minutes",
            {"payload": representative_payload()},
            admin_csrf,
        )
        self.assertEqual(status, 201)
        minute_id = admin_minute["id"]

        status, body, _ = self.request(advisor, "GET", "/api/minutes")
        self.assertEqual(status, 200)
        self.assertEqual(body["items"], [])

        status, _, _ = self.request(advisor, "GET", f"/api/minutes/{minute_id}")
        self.assertEqual(status, 404)

        status, _, _ = self.request(
            advisor, "DELETE", f"/api/minutes/{minute_id}", csrf=advisor_csrf
        )
        self.assertEqual(status, 403)

        status, _, _ = self.request(
            admin, "POST", "/api/minutes", {"payload": representative_payload()}
        )
        self.assertEqual(status, 403)

        status, body, _ = self.request(
            admin, "POST", "/api/minutes", {"payload": "datos inválidos"}, admin_csrf
        )
        self.assertEqual(status, 422)
        self.assertIn("payload", body["fieldErrors"])

        for field, value, expected_error in (
            ("precio_total", "NaN", "precio_total"),
            ("precio_total", 1_000_000_000, "precio_total"),
            ("numero_cuotas_total", "Infinity", "numero_cuotas_total"),
            ("numero_cuotas_total", 1.5, "numero_cuotas_total"),
            ("buyer_name", "X" * 241, "compradores.0.nombre_completo"),
        ):
            invalid = copy.deepcopy(representative_payload())
            if field == "buyer_name":
                invalid["compradores"][0]["nombre_completo"] = value
            else:
                invalid[field] = value
            status, body, _ = self.request(
                admin,
                "POST",
                "/api/minutes",
                {"payload": invalid},
                admin_csrf,
            )
            self.assertEqual(status, 422)
            self.assertIn(expected_error, body["fieldErrors"])

        status, incomplete, _ = self.request(
            advisor,
            "POST",
            "/api/minutes",
            {"payload": {"compradores": [{"nombre_completo": "Borrador"}]}},
            advisor_csrf,
        )
        self.assertEqual(status, 201)

        status, body, _ = self.request(
            advisor,
            "POST",
            f"/api/minutes/{incomplete['id']}/generate",
            {},
            advisor_csrf,
        )
        self.assertEqual(status, 422)
        self.assertTrue(body["fieldErrors"])

        status, document, headers = self.request(
            admin,
            "POST",
            f"/api/minutes/{minute_id}/generate",
            {},
            admin_csrf,
        )
        self.assertEqual(status, 200)
        self.assertTrue(document.startswith(b"PK"))
        self.assertGreater(len(document), 100_000)
        self.assertIn(".docx", headers["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(document)) as generated:
            self.assertIsNone(generated.testzip())
            xml_parts = b"".join(
                generated.read(name)
                for name in generated.namelist()
                if name.endswith(".xml")
            )
            self.assertIsNone(re.search(rb"\{\{[A-Z0-9_]+\}\}", xml_parts))
            document_xml = generated.read("word/document.xml")
            self.assertIn("ANA LUCÍA MENDOZA ROJAS".encode(), document_xml)
            self.assertIn("BRUNO ESTEBAN TORRES PAZ".encode(), document_xml)
            self.assertIn(b"CRONOGRAMA DE PAGOS", document_xml)
            self.assertNotIn(b'w:orient="landscape"', document_xml)
            self.assertIn(b'<w:pgSz w:w="11906" w:h="16838"/>', document_xml)
            self.assertIn(b"<w:tblHeader/>", document_xml)
            self.assertIn("word/media/cronograma-ayt-house.png", generated.namelist())
            self.assertIn("word/media/cronograma-villa-hermosa.png", generated.namelist())

        status, body, _ = self.request(admin, "GET", "/api/minutes")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["items"]), 2)

        status, body, _ = self.request(advisor, "GET", "/api/users")
        self.assertEqual(status, 403)

        status, _, _ = self.request(
            admin, "DELETE", f"/api/minutes/{minute_id}", csrf=admin_csrf
        )
        self.assertEqual(status, 204)
        status, replacement, _ = self.request(
            admin,
            "POST",
            "/api/minutes",
            {"payload": representative_payload()},
            admin_csrf,
        )
        self.assertEqual(status, 201)
        self.assertTrue(replacement["reference"].endswith("-0003"))

        admin_user = self.database.get_user_by_email(
            self.credentials["Administrador"]["email"]
        )
        assert admin_user is not None
        payload = normalize_payload(representative_payload())
        with ThreadPoolExecutor(max_workers=6) as pool:
            created = list(
                pool.map(
                    lambda _: self.database.create_minute(admin_user["id"], payload),
                    range(12),
                )
            )
        references = [item["reference"] for item in created]
        self.assertEqual(len(references), len(set(references)))

        credential = self.credentials["Administrador"]
        LOGIN_LIMITER.reset("ip:127.0.0.1")
        LOGIN_LIMITER.reset(f"account:{credential['email']}")
        barrier = threading.Barrier(20)

        def failed_login(_: int) -> int:
            opener = build_opener(HTTPCookieProcessor(CookieJar()))
            barrier.wait(timeout=5)
            status, _, _ = self.request(
                opener,
                "POST",
                "/api/login",
                {"email": credential["email"], "password": "incorrecta"},
            )
            return status

        with ThreadPoolExecutor(max_workers=20) as pool:
            statuses = list(pool.map(failed_login, range(20)))
        self.assertEqual(statuses.count(401), 8)
        self.assertEqual(statuses.count(429), 12)


if __name__ == "__main__":
    unittest.main()
