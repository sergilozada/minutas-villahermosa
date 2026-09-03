from __future__ import annotations

import io
import calendar
import re
import zipfile
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from xml.sax.saxutils import escape

from .config import STATIC_DIR, TEMPLATE_PATH
from .schema import load_schema


MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

AYT_LOGO_PATH = STATIC_DIR / "assets" / "ayt-house-logo.png"
VILLA_LOGO_PATH = STATIC_DIR / "assets" / "villa-hermosa-wordmark.png"
AYT_LOGO_REL = "rIdCronogramaAyt"
VILLA_LOGO_REL = "rIdCronogramaVilla"
AYT_LOGO_PART = "word/media/cronograma-ayt-house.png"
VILLA_LOGO_PART = "word/media/cronograma-villa-hermosa.png"
INITIAL_PAYMENT_ACCOUNT = "4003008478638"
INITIAL_PAYMENT_CCI = "00340000300847863890"
INITIAL_PAYMENT_BANK = "Interbank"
INITIAL_PAYMENT_BENEFICIARY = "EMPRESA INMOBILIARIA A&T HOUSE S.A.C."

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PICTURE_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
IMAGE_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
)

UNITS = (
    "cero",
    "uno",
    "dos",
    "tres",
    "cuatro",
    "cinco",
    "seis",
    "siete",
    "ocho",
    "nueve",
)

SPECIAL = {
    10: "diez",
    11: "once",
    12: "doce",
    13: "trece",
    14: "catorce",
    15: "quince",
    16: "dieciséis",
    17: "diecisiete",
    18: "dieciocho",
    19: "diecinueve",
    20: "veinte",
    21: "veintiuno",
    22: "veintidós",
    23: "veintitrés",
    24: "veinticuatro",
    25: "veinticinco",
    26: "veintiséis",
    27: "veintisiete",
    28: "veintiocho",
    29: "veintinueve",
}

TENS = {
    30: "treinta",
    40: "cuarenta",
    50: "cincuenta",
    60: "sesenta",
    70: "setenta",
    80: "ochenta",
    90: "noventa",
}

HUNDREDS = {
    100: "cien",
    200: "doscientos",
    300: "trescientos",
    400: "cuatrocientos",
    500: "quinientos",
    600: "seiscientos",
    700: "setecientos",
    800: "ochocientos",
    900: "novecientos",
}


class DocumentGenerationError(RuntimeError):
    pass


def _under_thousand(number: int) -> str:
    if number < 10:
        return UNITS[number]
    if number < 30:
        return SPECIAL[number]
    if number < 100:
        tens, unit = divmod(number, 10)
        base = TENS[tens * 10]
        return base if unit == 0 else f"{base} y {UNITS[unit]}"
    if number in HUNDREDS:
        return HUNDREDS[number]
    hundred, rest = divmod(number, 100)
    base = "ciento" if hundred == 1 else HUNDREDS[hundred * 100]
    return f"{base} {_under_thousand(rest)}"


def integer_to_spanish(number: int) -> str:
    if number < 0:
        return f"menos {integer_to_spanish(abs(number))}"
    if number < 1000:
        return _under_thousand(number)
    if number < 1_000_000:
        thousands, rest = divmod(number, 1000)
        prefix = "mil" if thousands == 1 else f"{_under_thousand(thousands)} mil"
        return prefix if rest == 0 else f"{prefix} {_under_thousand(rest)}"
    if number < 1_000_000_000:
        millions, rest = divmod(number, 1_000_000)
        prefix = "un millón" if millions == 1 else f"{integer_to_spanish(millions)} millones"
        return prefix if rest == 0 else f"{prefix} {integer_to_spanish(rest)}"
    raise ValueError("El monto excede el rango admitido.")


def amount_in_words(value: Any) -> str:
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except InvalidOperation:
        return ""
    whole = int(amount)
    cents = int((amount - whole) * 100)
    words = integer_to_spanish(whole)
    if words.endswith("uno"):
        words = words[:-3] + "un"
    return f"{words} con {cents:02d}/100 soles"


def format_currency(value: Any) -> str:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        return ""
    return f"S/ {amount:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


def format_amount_number(value: Any) -> str:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        return ""
    return f"{amount:,.2f}"


def amount_integer_words(value: Any) -> str:
    try:
        whole = int(Decimal(str(value or 0)))
    except (InvalidOperation, TypeError):
        return ""
    return integer_to_spanish(whole)


def amount_cents(value: Any) -> str:
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        return ""
    return f"{int((amount - int(amount)) * 100):02d}"


def long_date(value: Any) -> str:
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        return str(value or "")
    return f"{parsed.day} de {MONTHS[parsed.month - 1]} de {parsed.year}"


def _transform(value: Any, binding: dict[str, Any]) -> str:
    transform = binding.get("transform", "text")
    if transform == "uppercase":
        return str(value or "").upper()
    if transform == "lowercase":
        return str(value or "").lower()
    if transform == "title":
        return str(value or "").title()
    if transform == "date_long":
        return long_date(value)
    if transform == "currency":
        return format_currency(value)
    if transform == "amount_number":
        return format_amount_number(value)
    if transform == "amount_integer_words_upper":
        return amount_integer_words(value).upper()
    if transform == "amount_cents":
        return amount_cents(value)
    if transform == "amount_words":
        return amount_in_words(value)
    if transform == "integer":
        try:
            return str(int(float(value)))
        except (TypeError, ValueError):
            return ""
    if transform == "integer_words":
        try:
            return integer_to_spanish(int(float(value)))
        except (TypeError, ValueError):
            return ""
    if transform == "integer_words_upper":
        try:
            return integer_to_spanish(int(float(value))).upper()
        except (TypeError, ValueError):
            return ""
    if transform == "date_day":
        try:
            return str(date.fromisoformat(str(value)).day)
        except ValueError:
            return ""
    if transform == "date_month":
        try:
            parsed = date.fromisoformat(str(value))
            return MONTHS[parsed.month - 1]
        except ValueError:
            return ""
    if transform == "date_year":
        try:
            return str(date.fromisoformat(str(value)).year)
        except ValueError:
            return ""
    if transform == "yes_no":
        return "SÍ" if bool(value) else "NO"
    return str(value or "")


def build_replacements(payload: dict[str, Any]) -> dict[str, str]:
    replacements: dict[str, str] = {}
    for binding in load_schema().get("bindings", []):
        if "value" in binding:
            value: Any = binding["value"]
        else:
            value = payload.get(binding.get("field", ""), "")
        value_map = binding.get("map")
        if isinstance(value_map, dict):
            value = value_map.get(str(value), binding.get("default", ""))
        replacements[binding["token"]] = _transform(value, binding)
    return replacements


def _run_xml(
    text: Any,
    *,
    bold: bool = False,
    color: str | None = None,
    size: int = 18,
    font: str = "Arial",
) -> str:
    properties = [
        f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:cs="{font}"/>',
        f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>',
    ]
    if bold:
        properties.append("<w:b/><w:bCs/>")
    if color:
        properties.append(f'<w:color w:val="{color}"/>')
    return (
        f"<w:r><w:rPr>{''.join(properties)}</w:rPr>"
        f'<w:t xml:space="preserve">{escape(str(text or ""))}</w:t></w:r>'
    )


def _paragraph_xml(
    runs: list[str],
    *,
    align: str = "left",
    before: int = 0,
    after: int = 80,
    keep_next: bool = False,
    left_indent: int = 0,
    hanging: int = 0,
) -> str:
    keep = "<w:keepNext/><w:keepLines/>" if keep_next else ""
    indent = (
        f'<w:ind w:left="{left_indent}" w:hanging="{hanging}"/>'
        if left_indent or hanging
        else ""
    )
    return (
        "<w:p><w:pPr>"
        f'<w:spacing w:before="{before}" w:after="{after}" '
        'w:line="240" w:lineRule="auto"/>'
        f'<w:jc w:val="{align}"/>{keep}{indent}'
        f"</w:pPr>{''.join(runs)}</w:p>"
    )


def _buyer_description_runs(buyer: dict[str, Any]) -> list[str]:
    identified = "identificada" if buyer.get("genero") == "femenino" else "identificado"
    return [
        _run_xml(
            str(buyer.get("nombre_completo", "")).upper(),
            bold=True,
            size=20,
            font="Century Schoolbook",
        ),
        _run_xml(f", {identified} con DNI ", size=20, font="Century Schoolbook"),
        _run_xml(buyer.get("documento"), bold=True, size=20, font="Century Schoolbook"),
        _run_xml(", de nacionalidad ", size=20, font="Century Schoolbook"),
        _run_xml(
            str(buyer.get("nacionalidad", "")).upper(),
            bold=True,
            size=20,
            font="Century Schoolbook",
        ),
        _run_xml(", de profesión u ocupación ", size=20, font="Century Schoolbook"),
        _run_xml(
            str(buyer.get("ocupacion", "")).upper(),
            bold=True,
            size=20,
            font="Century Schoolbook",
        ),
        _run_xml(", de estado civil ", size=20, font="Century Schoolbook"),
        _run_xml(
            str(buyer.get("estado_civil", "")).upper(),
            bold=True,
            size=20,
            font="Century Schoolbook",
        ),
        _run_xml(", con domicilio ", size=20, font="Century Schoolbook"),
        _run_xml(
            str(buyer.get("domicilio", "")).upper(),
            bold=True,
            size=20,
            font="Century Schoolbook",
        ),
        _run_xml(", distrito ", size=20, font="Century Schoolbook"),
        _run_xml(
            str(buyer.get("distrito", "")).upper(),
            bold=True,
            size=20,
            font="Century Schoolbook",
        ),
        _run_xml(", provincia ", size=20, font="Century Schoolbook"),
        _run_xml(
            str(buyer.get("provincia", "")).upper(),
            bold=True,
            size=20,
            font="Century Schoolbook",
        ),
        _run_xml(" y departamento ", size=20, font="Century Schoolbook"),
        _run_xml(
            str(buyer.get("departamento", "")).upper(),
            bold=True,
            size=20,
            font="Century Schoolbook",
        ),
    ]


def _buyer_block_xml(payload: dict[str, Any]) -> str:
    raw_buyers = payload.get("compradores", [])
    buyers = (
        [buyer for buyer in raw_buyers if isinstance(buyer, dict)]
        if isinstance(raw_buyers, list)
        else []
    )

    if len(buyers) > 1:
        runs = [_run_xml("□ ", size=20, font="Segoe UI Symbol")]
        for index, buyer in enumerate(buyers):
            if index:
                connector = " y " if index == len(buyers) - 1 else ", "
                runs.append(_run_xml(connector, size=20, font="Century Schoolbook"))
            runs.extend(_buyer_description_runs(buyer))
        runs.extend(
            [
                _run_xml(
                    " a quienes en adelante se les denominará ",
                    size=20,
                    font="Century Schoolbook",
                ),
                _run_xml(
                    "LOS COMPRADORES",
                    bold=True,
                    size=20,
                    font="Century Schoolbook",
                ),
                _run_xml(". ========", size=20, font="Century Schoolbook"),
            ]
        )
        return _paragraph_xml(
            runs,
            align="both",
            after=0,
            left_indent=360,
            hanging=240,
        )

    paragraphs: list[str] = []
    for buyer in buyers:
        paragraphs.append(
            _paragraph_xml(
                [
                    _run_xml("□ ", size=20, font="Segoe UI Symbol"),
                    *_buyer_description_runs(buyer),
                    _run_xml(".", size=20, font="Century Schoolbook"),
                ],
                align="both",
                after=0,
                left_indent=360,
                hanging=240,
            )
        )
    paragraphs.append(
        _paragraph_xml(
            [
                _run_xml(
                    "A quien en adelante se le denominará ",
                    size=20,
                    font="Century Schoolbook",
                ),
                _run_xml("EL COMPRADOR", bold=True, size=20, font="Century Schoolbook"),
                _run_xml(". ========", size=20, font="Century Schoolbook"),
            ],
            align="both",
            after=0,
        )
    )
    return "".join(paragraphs)


def _replace_buyer_block(document_xml: str, payload: dict[str, Any]) -> str:
    raw_buyers = payload.get("compradores", [])
    buyers = (
        [buyer for buyer in raw_buyers if isinstance(buyer, dict)]
        if isinstance(raw_buyers, list)
        else []
    )
    if len(buyers) > 1:
        heading = "<w:t>EL COMPRADOR:</w:t>"
        heading_start = document_xml.find(heading)
        if heading_start < 0:
            raise DocumentGenerationError("No se encontró el encabezado interno del comprador.")
        paragraph_start = document_xml.rfind("<w:p", 0, heading_start)
        paragraph_end = document_xml.find("</w:p>", heading_start)
        if paragraph_start < 0 or paragraph_end < 0:
            raise DocumentGenerationError("El encabezado interno del comprador no es válido.")
        paragraph_end += len("</w:p>")
        heading_paragraph = document_xml[paragraph_start:paragraph_end].replace(
            heading,
            "<w:t>LOS COMPRADORES:</w:t>",
            1,
        )
        heading_paragraph, fill_count = re.subn(
            r'(<w:t xml:space="preserve"> )=+(</w:t>)',
            lambda match: f'{match.group(1)}{"=" * 48}{match.group(2)}',
            heading_paragraph,
            count=1,
        )
        if fill_count != 1:
            raise DocumentGenerationError("El encabezado interno no contiene su línea decorativa.")
        document_xml = (
            document_xml[:paragraph_start]
            + heading_paragraph
            + document_xml[paragraph_end:]
        )
    pattern = re.compile(
        r"<w:p\b[^>]*>(?:(?!</w:p>).)*\{\{BUYERS_BLOCK\}\}"
        r"(?:(?!</w:p>).)*</w:p>",
        re.DOTALL,
    )
    updated, count = pattern.subn(_buyer_block_xml(payload), document_xml, count=1)
    if count != 1:
        raise DocumentGenerationError("No se encontró el bloque interno de compradores.")
    return updated


def _payment_method_runs(payment: dict[str, Any]) -> list[str]:
    method = str(payment.get("metodo", ""))
    if method == "yape":
        return [_run_xml("mediante Yape", bold=True, size=20, font="Century Schoolbook")]
    if method == "plin":
        return [_run_xml("mediante Plin", bold=True, size=20, font="Century Schoolbook")]
    if method == "deposito_cuenta":
        description = (
            f"mediante depósito a la cuenta N.° {INITIAL_PAYMENT_ACCOUNT} "
            f"del Banco {INITIAL_PAYMENT_BANK}, a nombre de {INITIAL_PAYMENT_BENEFICIARY}"
        )
        return [_run_xml(description, size=20, font="Century Schoolbook")]
    if method == "transferencia_bancaria":
        description = (
            f"mediante transferencia bancaria a la cuenta N.° {INITIAL_PAYMENT_ACCOUNT} "
            f"del Banco {INITIAL_PAYMENT_BANK}, "
            f"a nombre de {INITIAL_PAYMENT_BENEFICIARY}"
        )
        return [_run_xml(description, size=20, font="Century Schoolbook")]
    if method == "transferencia_interbancaria":
        description = (
            f"mediante transferencia interbancaria a la cuenta N.° {INITIAL_PAYMENT_CCI} "
            f"del Banco {INITIAL_PAYMENT_BANK}, "
            f"a nombre de {INITIAL_PAYMENT_BENEFICIARY}"
        )
        return [_run_xml(description, size=20, font="Century Schoolbook")]
    raise DocumentGenerationError("Uno de los pagos iniciales tiene un método no admitido.")


def _payment_detail_runs(
    payment: dict[str, Any],
    *,
    include_amount: bool,
) -> list[str]:
    runs: list[str] = []
    if include_amount:
        amount = payment.get("monto")
        runs.extend(
            [
                _run_xml("S/ ", size=20, font="Century Schoolbook"),
                _run_xml(format_amount_number(amount), bold=True, size=20, font="Century Schoolbook"),
                _run_xml(
                    f" ({amount_integer_words(amount).upper()} con {amount_cents(amount)}/100 soles), ",
                    size=20,
                    font="Century Schoolbook",
                ),
            ]
        )
    runs.extend(_payment_method_runs(payment))
    runs.extend(
        [
            _run_xml(" con número de operación ", size=20, font="Century Schoolbook"),
            _run_xml(
                str(payment.get("numero_operacion", "")).upper(),
                bold=True,
                size=20,
                font="Century Schoolbook",
            ),
            _run_xml(", de fecha ", size=20, font="Century Schoolbook"),
            _run_xml(
                long_date(payment.get("fecha_pago")),
                bold=True,
                size=20,
                font="Century Schoolbook",
            ),
        ]
    )
    return runs


def _initial_payments_clause_xml(payload: dict[str, Any]) -> str:
    payments = [
        item
        for item in payload.get("pagos_iniciales", [])
        if isinstance(item, dict)
    ]
    # sorted() conserva el orden de ingreso cuando dos pagos comparten fecha.
    payments = sorted(
        payments,
        key=lambda item: date.fromisoformat(str(item.get("fecha_pago", ""))),
    )
    if not payments:
        raise DocumentGenerationError("No se registraron los pagos de la cuota inicial.")
    initial = payload.get("cuota_inicial")
    intro_runs = [
        _run_xml("3.2.1  La suma de S/ ", size=20, font="Century Schoolbook"),
        _run_xml(format_amount_number(initial), bold=True, size=20, font="Century Schoolbook"),
        _run_xml(
            f" ({amount_integer_words(initial).upper()} con {amount_cents(initial)}/100 soles), "
            "en concepto de cuota inicial, ",
            size=20,
            font="Century Schoolbook",
        ),
    ]
    if len(payments) == 1:
        intro_runs.append(
            _run_xml("pago que fue efectuado ", size=20, font="Century Schoolbook")
        )
        intro_runs.extend(_payment_detail_runs(payments[0], include_amount=False))
        intro_runs.append(_run_xml(". ========", size=20, font="Century Schoolbook"))
        return _paragraph_xml(intro_runs, align="both", after=0)

    intro_runs.append(
        _run_xml(
            "pago que fue efectuado, ",
            size=20,
            font="Century Schoolbook",
        )
    )
    runs = list(intro_runs)
    for index, payment in enumerate(payments, start=1):
        runs.extend(_payment_detail_runs(payment, include_amount=True))
        if index < len(payments):
            separator = " y " if index == len(payments) - 1 else ", "
            runs.append(_run_xml(separator, size=20, font="Century Schoolbook"))
    runs.append(_run_xml(". ========", size=20, font="Century Schoolbook"))
    return _paragraph_xml(runs, align="both", after=0)


def _replace_initial_payments_clause(document_xml: str, payload: dict[str, Any]) -> str:
    pattern = re.compile(
        r"<w:p\b[^>]*>(?:(?!</w:p>).)*\{\{INITIAL_AMOUNT\}\}"
        r"(?:(?!</w:p>).)*</w:p>",
        re.DOTALL,
    )
    updated, count = pattern.subn(
        _initial_payments_clause_xml(payload),
        document_xml,
        count=1,
    )
    if count != 1:
        raise DocumentGenerationError("No se encontró la cláusula de la cuota inicial.")
    return updated


def _signature_cell_xml(role: str, name: str = "", document: str = "") -> str:
    line = (
        "<w:p><w:pPr>"
        '<w:spacing w:before="360" w:after="80"/>'
        '<w:keepNext/><w:pBdr><w:bottom w:val="single" w:sz="8" '
        'w:space="1" w:color="5B6675"/></w:pBdr>'
        "</w:pPr></w:p>"
    )
    paragraphs = [
        line,
        _paragraph_xml(
            [_run_xml(role, bold=True, color="132B50", size=17)],
            align="center",
            after=20 if name else 80,
            keep_next=bool(name),
        ),
    ]
    if name:
        paragraphs.append(
            _paragraph_xml(
                [_run_xml(name, bold=True, color="132B50", size=17)],
                align="center",
                after=20,
                keep_next=True,
            )
        )
    if document:
        paragraphs.append(
            _paragraph_xml(
                [_run_xml(f"DNI {document}", color="5B6675", size=15)],
                align="center",
                after=80,
            )
        )
    return "".join(paragraphs)


def _signature_block_xml(payload: dict[str, Any]) -> str:
    signers: list[tuple[str, str, str]] = [("EL VENDEDOR", "", "")]
    for buyer in payload.get("compradores", []):
        if not isinstance(buyer, dict):
            continue
        signers.append(
            (
                "EL COMPRADOR",
                str(buyer.get("nombre_completo", "")).upper(),
                str(buyer.get("documento", "")),
            )
        )
    rows: list[list[tuple[str, str | None]]] = []
    for index in range(0, len(signers), 2):
        pair = signers[index : index + 2]
        cells = [
            (_signature_cell_xml(role, name, document), None)
            for role, name, document in pair
        ]
        if len(cells) == 1:
            cells.append(("<w:p/>", None))
        rows.append(cells)
    return _table_xml(
        rows,
        [4050, 4050],
        border_color=None,
        cell_margin=180,
    )


def _replace_signature_block(document_xml: str, payload: dict[str, Any]) -> str:
    pattern = re.compile(
        r"<w:p\b[^>]*>(?:(?!</w:p>).)*\{\{SIGNATURES_BLOCK\}\}"
        r"(?:(?!</w:p>).)*</w:p>",
        re.DOTALL,
    )
    updated, count = pattern.subn(_signature_block_xml(payload), document_xml, count=1)
    if count != 1:
        raise DocumentGenerationError("No se encontró el bloque interno de firmas.")
    return updated


def _image_run_xml(
    relationship_id: str,
    *,
    name: str,
    description: str,
    width_emu: int,
    height_emu: int,
    drawing_id: int,
) -> str:
    return f"""
<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">
  <wp:extent cx="{width_emu}" cy="{height_emu}"/>
  <wp:effectExtent l="0" t="0" r="0" b="0"/>
  <wp:docPr id="{drawing_id}" name="{name}" descr="{description}"/>
  <wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>
  <a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
    <pic:pic>
      <pic:nvPicPr><pic:cNvPr id="0" name="{name}" descr="{description}"/><pic:cNvPicPr/></pic:nvPicPr>
      <pic:blipFill><a:blip r:embed="{relationship_id}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
      <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{width_emu}" cy="{height_emu}"/></a:xfrm>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
      </pic:spPr>
    </pic:pic>
  </a:graphicData></a:graphic>
</wp:inline></w:drawing></w:r>"""


def _table_xml(
    rows: list[list[tuple[str, str | None]]],
    widths: list[int],
    *,
    border_color: str | None = "D9E2E5",
    header_rows: int = 0,
    cell_margin: int = 100,
    indent: int = 120,
) -> str:
    total_width = sum(widths)
    border_attributes = (
        f'w:val="single" w:sz="4" w:space="0" w:color="{border_color}"'
        if border_color
        else 'w:val="nil"'
    )
    borders = "".join(
        f"<w:{edge} {border_attributes}/>"
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    table_properties = (
        f'<w:tblW w:w="{total_width}" w:type="dxa"/>'
        f'<w:tblInd w:w="{indent}" w:type="dxa"/>'
        '<w:tblLayout w:type="fixed"/>'
        f"<w:tblBorders>{borders}</w:tblBorders>"
        "<w:tblCellMar>"
        f'<w:top w:w="{cell_margin}" w:type="dxa"/>'
        f'<w:left w:w="{cell_margin}" w:type="dxa"/>'
        f'<w:bottom w:w="{cell_margin}" w:type="dxa"/>'
        f'<w:right w:w="{cell_margin}" w:type="dxa"/>'
        "</w:tblCellMar>"
    )
    grid = "".join(f'<w:gridCol w:w="{width}"/>' for width in widths)
    row_xml: list[str] = []
    for row_index, row in enumerate(rows):
        row_properties = "<w:cantSplit/>"
        if row_index < header_rows:
            row_properties += "<w:tblHeader/>"
        cells: list[str] = []
        for column_index, (content, fill) in enumerate(row):
            shade = f'<w:shd w:val="clear" w:fill="{fill}"/>' if fill else ""
            cells.append(
                "<w:tc><w:tcPr>"
                f'<w:tcW w:w="{widths[column_index]}" w:type="dxa"/>'
                f'{shade}<w:vAlign w:val="center"/>'
                f"</w:tcPr>{content}</w:tc>"
            )
        row_xml.append(
            f"<w:tr><w:trPr>{row_properties}</w:trPr>{''.join(cells)}</w:tr>"
        )
    return (
        f"<w:tbl><w:tblPr>{table_properties}</w:tblPr>"
        f"<w:tblGrid>{grid}</w:tblGrid>{''.join(row_xml)}</w:tbl>"
    )


def _label_value_paragraph(label: str, value: Any) -> str:
    display = str(value).strip() if value not in (None, "") else "—"
    return _paragraph_xml(
        [
            _run_xml(f"{label}: ", bold=True, color="132B50", size=18),
            _run_xml(display, color="182536", size=18),
        ],
        after=40,
    )


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _schedule_table_xml(payload: dict[str, Any]) -> str:
    total = int(float(payload.get("numero_cuotas_total", 0)))
    regular_count = int(float(payload.get("numero_cuotas_regulares", 0)))
    first_due = date.fromisoformat(str(payload.get("fecha_primera_cuota")))
    widths = [456, 1333, 1158, 772, 1158, 1333, 1018, 1712, 1712]
    headers = [
        "N.°",
        "Vencimiento",
        "Monto",
        "Mora",
        "Total",
        "Fecha de pago",
        "Estado",
        "Voucher",
        "Boleta",
    ]
    rows: list[list[tuple[str, str | None]]] = [
        [
            (
                _paragraph_xml(
                    [_run_xml(label, bold=True, color="FFFFFF", size=14)],
                    align="center",
                    after=0,
                    keep_next=True,
                ),
                "132B50",
            )
            for label in headers
        ]
    ]
    for index in range(total):
        due = _add_months(first_due, index)
        is_final = index >= regular_count
        amount = (
            payload.get("monto_cuota_final")
            if is_final
            else payload.get("monto_cuota_regular")
        )
        fill = "FFF4D6" if is_final else ("F3F8F8" if index % 2 else None)
        values = [
            str(index + 1),
            due.strftime("%d/%m/%Y"),
            format_currency(amount),
            "S/ 0,00",
            format_currency(amount),
            "",
            "Pendiente",
            "",
            "",
        ]
        rows.append(
            [
                (
                    _paragraph_xml(
                        [
                            _run_xml(
                                value,
                                bold=is_final and column in {0, 2, 4},
                                color="182536",
                                size=14,
                            )
                        ],
                        align="center",
                        after=0,
                    ),
                    fill,
                )
                for column, value in enumerate(values)
            ]
        )
    return _table_xml(rows, widths, header_rows=1, cell_margin=80)


def _schedule_xml(payload: dict[str, Any]) -> str:
    buyers = [
        item for item in payload.get("compradores", []) if isinstance(item, dict)
    ]
    logo_table = _table_xml(
        [[
            (
                _paragraph_xml(
                    [
                        _image_run_xml(
                            AYT_LOGO_REL,
                            name="AYT House Inmobiliaria",
                            description="Logotipo de AYT House Inmobiliaria",
                            width_emu=1_143_000,
                            height_emu=1_143_000,
                            drawing_id=2101,
                        )
                    ],
                    align="left",
                    after=0,
                ),
                None,
            ),
            (
                _paragraph_xml(
                    [
                        _image_run_xml(
                            VILLA_LOGO_REL,
                            name="Condominio Villa Hermosa",
                            description="Logotipo del Condominio Villa Hermosa",
                            width_emu=1_829_000,
                            height_emu=749_000,
                            drawing_id=2102,
                        )
                    ],
                    align="right",
                    after=0,
                ),
                None,
            ),
        ]],
        [5326, 5326],
        border_color=None,
        cell_margin=0,
    )
    title = _paragraph_xml(
        [_run_xml("CRONOGRAMA DE PAGOS", bold=True, color="132B50", size=34)],
        align="center",
        before=120,
        after=120,
        keep_next=True,
    )
    phone_bar = _table_xml(
        [[(
            _paragraph_xml(
                [
                    _run_xml(
                        "Teléfono de cobranza Villa Hermosa: 929 074 799",
                        bold=True,
                        color="132B50",
                        size=19,
                    )
                ],
                align="center",
                after=0,
                keep_next=True,
            ),
            "F2C230",
        )]],
        [10652],
        border_color=None,
        cell_margin=90,
    )

    client_lines: list[str] = []
    for index, buyer in enumerate(buyers):
        label = "Comprador" if len(buyers) == 1 else f"Comprador {index + 1}"
        client_lines.append(
            _label_value_paragraph(
                label,
                f"{buyer.get('nombre_completo', '')}  ·  DNI {buyer.get('documento', '')}",
            )
        )
    contact_phone = next(
        (str(item.get("telefono", "")).strip() for item in buyers if str(item.get("telefono", "")).strip()),
        "—",
    )
    contact_email = next(
        (str(item.get("email", "")).strip() for item in buyers if str(item.get("email", "")).strip()),
        "—",
    )
    client_lines.extend(
        [
            _label_value_paragraph("Celular de contacto", contact_phone),
            _label_value_paragraph("Correo de contacto", contact_email),
            _label_value_paragraph("Precio total", format_currency(payload.get("precio_total"))),
            _label_value_paragraph("Moneda", "SOLES"),
            _label_value_paragraph("Proyecto", "Condominio Villa Hermosa"),
            _label_value_paragraph("Manzana", payload.get("manzana")),
            _label_value_paragraph("Lote", payload.get("lote")),
            _label_value_paragraph("Metraje", f"{payload.get('area_m2', '')} m²"),
        ]
    )
    bank_lines = [
        _paragraph_xml(
            [_run_xml("DATOS PARA PAGOS", bold=True, color="132B50", size=20)],
            after=100,
            keep_next=True,
        ),
        _label_value_paragraph("Banco", "INTERBANK"),
        _label_value_paragraph("N.° de cuenta", "4003008478638"),
        _label_value_paragraph("CCI", "00340000300847863890"),
        _paragraph_xml(
            [
                _run_xml(
                    "EMPRESA INMOBILIARIA A&T HOUSE S.A.C.",
                    bold=True,
                    color="132B50",
                    size=18,
                )
            ],
            before=60,
            after=40,
        ),
    ]
    metadata = _table_xml(
        [[
            ("".join(client_lines), None),
            ("".join(bank_lines), "DDEEDB"),
        ]],
        [6386, 4266],
        border_color=None,
        cell_margin=180,
    )
    detail_heading = _paragraph_xml(
        [_run_xml("DETALLE DE CUOTAS", bold=True, color="148E98", size=22)],
        before=160,
        after=80,
        keep_next=True,
    )
    return "".join(
        [logo_table, title, phone_bar, metadata, detail_heading, _schedule_table_xml(payload)]
    )


def _append_schedule(document_xml: str, payload: dict[str, Any]) -> str:
    section_match = re.search(
        r"(<w:sectPr\b.*?</w:sectPr>)\s*</w:body>", document_xml, re.DOTALL
    )
    if section_match is None:
        raise DocumentGenerationError("La plantilla no contiene una sección válida.")
    portrait_section = section_match.group(1)
    if "<w:type" not in portrait_section:
        portrait_section = portrait_section.replace(
            "</w:sectPr>", '<w:type w:val="nextPage"/></w:sectPr>'
        )
    section_break = f"<w:p><w:pPr>{portrait_section}</w:pPr></w:p>"
    schedule_section = (
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="567" w:right="567" w:bottom="567" w:left="567" '
        'w:header="360" w:footer="360" w:gutter="0"/>'
        '<w:cols w:space="708"/><w:docGrid w:linePitch="360"/>'
        "</w:sectPr>"
    )
    replacement = section_break + _schedule_xml(payload) + schedule_section
    start, end = section_match.span(1)
    updated = document_xml[:start] + replacement + document_xml[end:]
    namespace_anchor = 'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
    if "xmlns:a=" not in updated:
        updated = updated.replace(
            namespace_anchor,
            namespace_anchor
            + f' xmlns:a="{DRAWING_NS}" xmlns:pic="{PICTURE_NS}"',
            1,
        )
    return updated


def _patch_document_relationships(data: bytes) -> bytes:
    text = data.decode("utf-8")
    additions = (
        f'<Relationship Id="{AYT_LOGO_REL}" Type="{IMAGE_REL_TYPE}" '
        'Target="media/cronograma-ayt-house.png"/>'
        f'<Relationship Id="{VILLA_LOGO_REL}" Type="{IMAGE_REL_TYPE}" '
        'Target="media/cronograma-villa-hermosa.png"/>'
    )
    if AYT_LOGO_REL not in text:
        text = text.replace("</Relationships>", additions + "</Relationships>")
    return text.encode("utf-8")


def _patch_content_types(data: bytes) -> bytes:
    text = data.decode("utf-8")
    if 'Extension="png"' not in text:
        text = text.replace(
            "</Types>",
            '<Default Extension="png" ContentType="image/png"/></Types>',
        )
    return text.encode("utf-8")


def generate_docx(payload: dict[str, Any]) -> bytes:
    if not TEMPLATE_PATH.exists():
        raise DocumentGenerationError("No se encontró la plantilla interna de la minuta.")
    if not AYT_LOGO_PATH.exists() or not VILLA_LOGO_PATH.exists():
        raise DocumentGenerationError("No se encontraron los logos internos del cronograma.")
    try:
        replacements = build_replacements(payload)
    except (ArithmeticError, ValueError, OverflowError) as error:
        raise DocumentGenerationError(
            "Uno de los valores excede el rango admitido por la minuta."
        ) from error
    output = io.BytesIO()
    with zipfile.ZipFile(TEMPLATE_PATH, "r") as source, zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED
    ) as target:
        source_names = set(source.namelist())
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == "word/document.xml":
                text = data.decode("utf-8")
                text = _replace_buyer_block(text, payload)
                text = _replace_signature_block(text, payload)
                text = _replace_initial_payments_clause(text, payload)
                for token, value in replacements.items():
                    text = text.replace(token, escape(value))
                text = _append_schedule(text, payload)
                data = text.encode("utf-8")
            elif item.filename.startswith("word/") and item.filename.endswith(".xml"):
                text = data.decode("utf-8")
                for token, value in replacements.items():
                    text = text.replace(token, escape(value))
                data = text.encode("utf-8")
            elif item.filename == "word/_rels/document.xml.rels":
                data = _patch_document_relationships(data)
            elif item.filename == "[Content_Types].xml":
                data = _patch_content_types(data)
            target.writestr(item, data)
        if AYT_LOGO_PART not in source_names:
            target.writestr(AYT_LOGO_PART, AYT_LOGO_PATH.read_bytes())
        if VILLA_LOGO_PART not in source_names:
            target.writestr(VILLA_LOGO_PART, VILLA_LOGO_PATH.read_bytes())
    result = output.getvalue()
    remaining: set[bytes] = set()
    with zipfile.ZipFile(io.BytesIO(result), "r") as generated:
        for name in generated.namelist():
            if name.endswith(".xml"):
                remaining.update(
                    re.findall(rb"\{\{[A-Z0-9_]+\}\}", generated.read(name))
                )
    remaining = sorted(remaining)
    if remaining:
        labels = ", ".join(token.decode("utf-8") for token in remaining[:8])
        raise DocumentGenerationError(f"La plantilla conserva campos sin mapear: {labels}")
    return result
