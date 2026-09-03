from __future__ import annotations

import json
import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
from typing import Any

from .config import SCHEMA_PATH


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def all_fields() -> dict[str, dict[str, Any]]:
    fields: dict[str, dict[str, Any]] = {}
    for section in load_schema().get("sections", []):
        if section.get("repeatable") is True:
            continue
        for field in section.get("fields", []):
            fields[field["id"]] = field
    return fields


def repeatable_sections() -> list[dict[str, Any]]:
    return [
        section
        for section in load_schema().get("sections", [])
        if section.get("repeatable") is True
    ]


def repeatable_groups() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for section in load_schema().get("sections", []):
        groups.extend(
            group
            for group in section.get("groups", [])
            if group.get("repeatable") is True
        )
    return groups


def buyer_section() -> dict[str, Any]:
    for section in repeatable_sections():
        if section.get("id") == "buyer":
            return section
    raise RuntimeError("El esquema no contiene la sección repetible de compradores.")


def _default_for_field(field: dict[str, Any]) -> Any:
    if "default" in field:
        return field["default"]
    if field.get("type") == "checkbox":
        return False
    return ""


def default_buyer() -> dict[str, Any]:
    return {
        field["id"]: _default_for_field(field)
        for field in buyer_section().get("fields", [])
    }


def default_payload() -> dict[str, Any]:
    defaults = {
        field_id: _default_for_field(field)
        for field_id, field in all_fields().items()
    }
    for section in repeatable_sections():
        payload_key = str(section.get("payloadKey") or section["id"])
        item = {
            field["id"]: _default_for_field(field)
            for field in section.get("fields", [])
        }
        defaults[payload_key] = [item]
    for group in repeatable_groups():
        payload_key = str(group.get("payloadKey") or group["id"])
        item = {
            field["id"]: _default_for_field(field)
            for field in group.get("fields", [])
        }
        defaults[payload_key] = [item]
    return defaults


def _normalize_field_value(field: dict[str, Any], value: Any) -> Any:
    if field.get("type") == "checkbox":
        return value
    if field.get("type") == "number":
        if isinstance(value, bool):
            return value
        if value in (None, ""):
            return ""
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return str(value).strip()
    return str(value or "").strip()


def _legacy_buyer(raw: dict[str, Any], fields: list[dict[str, Any]]) -> dict[str, Any] | None:
    legacy: dict[str, Any] = {}
    found = False
    for field in fields:
        field_id = field["id"]
        legacy_key = f"comprador_{field_id}"
        if legacy_key in raw:
            legacy[field_id] = raw[legacy_key]
            found = True
    return legacy if found else None


def normalize_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return default_payload()
    result = default_payload()
    for field_id, field in all_fields().items():
        value = raw.get(field_id, result[field_id])
        result[field_id] = _normalize_field_value(field, value)
    if raw.get("numero_cuotas_total") in (None, ""):
        legacy_value = raw.get("numero_cuotas_regulares")
        legacy_regular = _as_float(legacy_value)
        if legacy_regular is not None and legacy_regular.is_integer():
            result["numero_cuotas_total"] = int(legacy_regular) + 1
        elif legacy_value not in (None, ""):
            result["numero_cuotas_total"] = legacy_value

    for section in repeatable_sections():
        payload_key = str(section.get("payloadKey") or section["id"])
        fields = list(section.get("fields", []))
        raw_items = raw.get(payload_key)
        if payload_key in raw and not isinstance(raw_items, list):
            result[payload_key] = raw_items
            continue
        if payload_key not in raw:
            legacy = _legacy_buyer(raw, fields)
            raw_items = [legacy or {}]
        normalized_items: list[Any] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                normalized_items.append(raw_item)
                continue
            source = raw_item
            normalized_items.append(
                {
                    field["id"]: _normalize_field_value(
                        field, source.get(field["id"], _default_for_field(field))
                    )
                    for field in fields
                }
            )
        result[payload_key] = normalized_items

    for group in repeatable_groups():
        payload_key = str(group.get("payloadKey") or group["id"])
        fields = list(group.get("fields", []))
        raw_items = raw.get(payload_key)
        if payload_key in raw and not isinstance(raw_items, list):
            result[payload_key] = raw_items
            continue
        if payload_key not in raw:
            has_legacy_payment = any(
                raw.get(field_id) not in (None, "")
                for field_id in ("numero_operacion", "fecha_pago_inicial")
            )
            raw_items = [
                {
                    "metodo": "transferencia_bancaria",
                    "monto": raw.get("cuota_inicial", ""),
                    "numero_operacion": raw.get("numero_operacion", ""),
                    "fecha_pago": raw.get("fecha_pago_inicial", ""),
                }
            ] if has_legacy_payment else [{}]
        normalized_items = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                normalized_items.append(raw_item)
                continue
            normalized_items.append(
                {
                    field["id"]: _normalize_field_value(
                        field,
                        raw_item.get(field["id"], _default_for_field(field)),
                    )
                    for field in fields
                }
            )
        result[payload_key] = normalized_items
    return compute_payload(result)


def compute_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    price = _as_float(result.get("precio_total"))
    initial = _as_float(result.get("cuota_inicial"))
    total_count = _as_float(result.get("numero_cuotas_total"))
    regular_amount = _as_float(result.get("monto_cuota_regular"))

    if price is not None and initial is not None:
        result["saldo_financiado"] = round(price - initial, 2)
    else:
        result["saldo_financiado"] = ""

    if total_count is not None:
        result["numero_cuotas_regulares"] = max(int(total_count) - 1, 0)
    else:
        result["numero_cuotas_regulares"] = ""

    balance = _as_float(result.get("saldo_financiado"))
    regular_count = _as_float(result.get("numero_cuotas_regulares"))
    valid_total_count = (
        total_count is not None
        and total_count.is_integer()
        and total_count >= 1
    )
    if (
        regular_amount is None
        and balance is not None
        and balance > 0
        and valid_total_count
    ):
        result["monto_cuota_regular"] = round(balance / int(total_count), 2)
        regular_amount = _as_float(result.get("monto_cuota_regular"))
    if balance is not None and regular_count is not None and regular_amount is not None:
        result["monto_cuota_final"] = round(
            balance - int(regular_count) * regular_amount, 2
        )
    else:
        result["monto_cuota_final"] = ""

    payment_cents = [
        cents
        for item in result.get("pagos_iniciales", [])
        if isinstance(item, dict)
        for cents in [_as_money_cents(item.get("monto"))]
        if cents is not None
    ] if isinstance(result.get("pagos_iniciales"), list) else []
    result["total_pagos_iniciales"] = (
        round(sum(payment_cents) / 100, 2) if payment_cents else ""
    )
    return result


def _required(field: dict[str, Any], payload: dict[str, Any]) -> bool:
    if field.get("required") is True:
        return True
    condition = field.get("requiredWhen")
    if not isinstance(condition, dict):
        return False
    actual = payload.get(condition.get("field"))
    if "equals" in condition:
        return actual == condition["equals"]
    if "in" in condition:
        return actual in condition["in"]
    return False


def _missing_required_value(field: dict[str, Any], value: Any) -> bool:
    if value is None or value == "":
        return True
    return field.get("type") == "checkbox" and value is False


def validate_payload(
    payload: dict[str, Any], *, for_generation: bool = False
) -> dict[str, str]:
    errors: dict[str, str] = {}
    for field_id, field in all_fields().items():
        value = payload.get(field_id, "")
        enforce_required = for_generation or field.get("requiredOnSave") is True
        if enforce_required and _required(field, payload) and _missing_required_value(field, value):
            errors[field_id] = "Este campo es obligatorio."
            continue
        message = _validate_value(field, value)
        if message:
            errors[field_id] = message

    seen_documents: dict[str, str] = {}
    for section in repeatable_sections():
        payload_key = str(section.get("payloadKey") or section["id"])
        items = payload.get(payload_key, [])
        if not isinstance(items, list):
            errors[payload_key] = "Los compradores deben enviarse como una lista."
            continue
        minimum = int(section.get("minItems", 1))
        maximum = int(section.get("maxItems", 10))
        if for_generation and len(items) < minimum:
            errors[payload_key] = f"Registra al menos {minimum} comprador."
        elif len(items) > maximum:
            errors[payload_key] = f"Puedes registrar como máximo {maximum} compradores."
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors[f"{payload_key}.{index}"] = (
                    "Cada comprador debe contener un grupo de datos válido."
                )
                continue
            record = item if isinstance(item, dict) else {}
            for field in section.get("fields", []):
                field_id = field["id"]
                key = f"{payload_key}.{index}.{field_id}"
                value = record.get(field_id, "")
                enforce_required = for_generation or field.get("requiredOnSave") is True
                if enforce_required and _required(field, record) and _missing_required_value(field, value):
                    errors[key] = "Este campo es obligatorio."
                    continue
                message = _validate_value(field, value)
                if message:
                    errors[key] = message
            document = re.sub(r"\D", "", str(record.get("documento", "")))
            if len(document) == 8:
                if document in seen_documents:
                    errors[f"{payload_key}.{index}.documento"] = (
                        "Este DNI ya está registrado en otro comprador."
                    )
                else:
                    seen_documents[document] = f"{payload_key}.{index}.documento"

    for group in repeatable_groups():
        payload_key = str(group.get("payloadKey") or group["id"])
        items = payload.get(payload_key, [])
        if not isinstance(items, list):
            errors[payload_key] = "Los pagos iniciales deben enviarse como una lista."
            continue
        minimum = int(group.get("minItems", 1))
        maximum = int(group.get("maxItems", 20))
        if for_generation and len(items) < minimum:
            errors[payload_key] = f"Registra al menos {minimum} pago inicial."
        elif len(items) > maximum:
            errors[payload_key] = f"Puedes registrar como máximo {maximum} pagos iniciales."
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors[f"{payload_key}.{index}"] = (
                    "Cada pago debe contener un grupo de datos válido."
                )
                continue
            for field in group.get("fields", []):
                field_id = field["id"]
                key = f"{payload_key}.{index}.{field_id}"
                value = item.get(field_id, "")
                enforce_required = for_generation or field.get("requiredOnSave") is True
                if enforce_required and _required(field, item) and _missing_required_value(field, value):
                    errors[key] = "Este campo es obligatorio."
                    continue
                message = _validate_value(field, value)
                if message:
                    errors[key] = message

    price = _as_float(payload.get("precio_total"))
    initial = _as_float(payload.get("cuota_inicial"))
    financed = _as_float(payload.get("saldo_financiado"))
    if price is not None and initial is not None and initial > price:
        errors["cuota_inicial"] = "La cuota inicial no puede superar el precio total."
    if price is not None and initial is not None and financed is not None:
        if abs((price - initial) - financed) > 0.05:
            errors["saldo_financiado"] = (
                "El saldo debe ser igual al precio total menos la cuota inicial."
            )

    if for_generation and initial is not None:
        payments = payload.get("pagos_iniciales", [])
        if isinstance(payments, list) and payments:
            cents = [
                _as_money_cents(item.get("monto"))
                for item in payments
                if isinstance(item, dict)
            ]
            initial_cents = _as_money_cents(initial)
            if (
                initial_cents is not None
                and len(cents) == len(payments)
                and all(value is not None for value in cents)
                and sum(value for value in cents if value is not None) != initial_cents
            ):
                errors.setdefault(
                    "pagos_iniciales",
                    "La suma de los pagos iniciales debe coincidir exactamente con la cuota inicial.",
                )

    regular_count = _as_float(payload.get("numero_cuotas_regulares"))
    regular_amount = _as_float(payload.get("monto_cuota_regular"))
    final_amount = _as_float(payload.get("monto_cuota_final"))
    if final_amount is not None and final_amount <= 0:
        errors["monto_cuota_regular"] = (
            "La cuota final debe ser mayor a cero; ajusta el total o el monto regular."
        )
    if (
        financed is not None
        and regular_count is not None
        and regular_amount is not None
        and final_amount is not None
        and abs(financed - (int(regular_count) * regular_amount + final_amount)) > 0.05
    ):
        errors["monto_cuota_final"] = "La suma de las cuotas debe coincidir con el saldo."

    first_due_value = payload.get("fecha_primera_cuota")
    total_count = _as_float(payload.get("numero_cuotas_total"))
    if first_due_value not in (None, "") and total_count is not None and total_count >= 1:
        try:
            first_due = date.fromisoformat(str(first_due_value))
            last_month_index = first_due.month - 1 + int(total_count) - 1
            if first_due.year + last_month_index // 12 > date.max.year:
                errors["fecha_primera_cuota"] = (
                    "La fecha final del cronograma excede el calendario admitido."
                )
        except ValueError:
            pass

    if for_generation:
        required_tokens = load_schema().get("generationRequiredFields", [])
        for field_id in required_tokens:
            field = all_fields().get(field_id, {})
            if _missing_required_value(field, payload.get(field_id)):
                errors.setdefault(field_id, "Completa este dato antes de generar la minuta.")
    return errors


def _validate_value(field: dict[str, Any], value: Any) -> str:
    if value in (None, ""):
        return ""
    field_type = field.get("type")
    if field_type == "checkbox" and not isinstance(value, bool):
        return "Usa un valor verdadero o falso válido."
    if field_type in {"text", "email", "tel", "select"}:
        max_length = int(field.get("maxlength", 240))
        if len(str(value)) > max_length:
            return f"Usa como máximo {max_length} caracteres."
    if field_type == "email" and not re.fullmatch(
        r"[^\s@]+@[^\s@]+\.[^\s@]+", str(value)
    ):
        return "Ingresa un correo válido."
    if field_type == "select" and str(value) not in {
        str(option.get("value")) for option in field.get("options", [])
    }:
        return "Selecciona una opción válida."
    if field.get("validation") == "dni" and not re.fullmatch(
        r"\d{8}", re.sub(r"\D", "", str(value))
    ):
        return "El DNI debe tener 8 dígitos."
    if field_type == "date":
        try:
            date.fromisoformat(str(value))
        except ValueError:
            return "Ingresa una fecha válida."
    if field_type == "number":
        if isinstance(value, bool):
            return "Ingresa un número válido."
        try:
            numeric = float(value)
            if not math.isfinite(numeric):
                return "Ingresa un número finito."
            if field.get("integer") is True and not numeric.is_integer():
                return "Ingresa un número entero."
            if "min" in field and numeric < float(field["min"]):
                return f"El valor mínimo es {field['min']}."
            if "max" in field and numeric > float(field["max"]):
                return f"El valor máximo es {field['max']}."
        except (TypeError, ValueError):
            return "Ingresa un número válido."
    return ""


def _as_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _as_money_cents(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite():
        return None
    rounded = amount.quantize(Decimal("0.01"), ROUND_HALF_UP)
    return int(rounded * 100)
