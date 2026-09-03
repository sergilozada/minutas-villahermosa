from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path


EXPECTED_SOURCE_HASH = "06e75395a2d3429f15366936d7a2c26fe2686b02a40a463ad6d441368bb2ad4a"

TOKENS_IN_DOCUMENT_ORDER = [
    "{{BUYER_FULL_NAME}}",
    "{{BUYER_DNI}}",
    "{{BUYER_NATIONALITY}}",
    "{{BUYER_OCCUPATION}}",
    "{{BUYER_MARITAL_STATUS}}",
    "{{BUYER_ADDRESS}}",
    "{{BUYER_DISTRICT}}",
    "{{BUYER_PROVINCE}}",
    "{{BUYER_DEPARTMENT}}",
    "{{PROPERTY_LOT}}",
    "{{PROPERTY_BLOCK}}",
    "{{PROPERTY_AREA}}",
    "{{TOTAL_AMOUNT}}",
    "{{TOTAL_WORDS}}",
    "{{TOTAL_CENTS}}",
    "{{INITIAL_AMOUNT}}",
    "{{INITIAL_WORDS}}",
    "{{INITIAL_CENTS}}",
    "{{INITIAL_OPERATION}}",
    "{{INITIAL_DAY}}",
    "{{INITIAL_MONTH}}",
    "{{INITIAL_YEAR}}",
    "{{BALANCE_AMOUNT}}",
    "{{BALANCE_WORDS}}",
    "{{BALANCE_CENTS}}",
    "{{INSTALLMENTS_TOTAL}}",
    "{{INSTALLMENTS_TOTAL_WORDS}}",
    "{{INSTALLMENTS_REGULAR_COUNT}}",
    "{{INSTALLMENT_REGULAR_AMOUNT}}",
    "{{INSTALLMENT_REGULAR_WORDS}}",
    "{{INSTALLMENT_REGULAR_CENTS}}",
    "{{INSTALLMENT_FINAL_AMOUNT}}",
    "{{INSTALLMENT_FINAL_WORDS}}",
    "{{INSTALLMENT_FINAL_CENTS}}",
    "{{SIGNATURE_DAY}}",
    "{{SIGNATURE_MONTH}}",
    "{{SIGNATURE_YEAR}}",
]

BUYER_SOURCE_TOKENS = TOKENS_IN_DOCUMENT_ORDER[:9] + ["{{BUYER_IDENTIFIED_AS}}"]
TOKENS_IN_TEMPLATE = TOKENS_IN_DOCUMENT_ORDER[9:] + [
    "{{BUYERS_BLOCK}}",
    "{{SIGNATURES_BLOCK}}",
]

TEXT_NODE_PATTERN = re.compile(r"(<w:t(?:\s[^>]*)?>)(.*?)(</w:t>)", re.DOTALL)
PLACEHOLDER_PATTERN = re.compile(r"X{2,}")
PARAGRAPH_PATTERN = re.compile(r"(<w:p(?:\s[^>]*)?>.*?</w:p>)", re.DOTALL)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def patch_document_xml(data: bytes) -> bytes:
    xml = data.decode("utf-8")
    token_iterator = iter(TOKENS_IN_DOCUMENT_ORDER)
    replaced: list[str] = []

    def patch_text_node(match: re.Match[str]) -> str:
        text = match.group(2)

        def replace_placeholder(_: re.Match[str]) -> str:
            try:
                token = next(token_iterator)
            except StopIteration as error:
                raise RuntimeError("La plantilla contiene más marcadores que el mapa.") from error
            replaced.append(token)
            return token

        text = PLACEHOLDER_PATTERN.sub(replace_placeholder, text)
        return f"{match.group(1)}{text}{match.group(3)}"

    xml = TEXT_NODE_PATTERN.sub(patch_text_node, xml)
    try:
        unexpected = next(token_iterator)
    except StopIteration:
        unexpected = None
    if unexpected is not None:
        raise RuntimeError(
            f"La plantilla contiene menos marcadores que el mapa; falta {unexpected}."
        )
    if len(replaced) != 37:
        raise RuntimeError(f"Se esperaban 37 marcadores; se reemplazaron {len(replaced)}.")

    def replace_visible_text(fragment: str, search: str, replacement: str) -> str:
        nodes = list(TEXT_NODE_PATTERN.finditer(fragment))
        combined = "".join(node.group(2) for node in nodes)
        start = combined.find(search)
        if start < 0:
            raise RuntimeError(f"No se encontró el texto visible {search!r}.")
        end = start + len(search)
        cursor = 0
        start_index = end_index = -1
        start_offset = end_offset = 0
        for index, node in enumerate(nodes):
            node_text = node.group(2)
            node_end = cursor + len(node_text)
            if start_index < 0 and start < node_end:
                start_index = index
                start_offset = start - cursor
            if end <= node_end:
                end_index = index
                end_offset = end - cursor
                break
            cursor = node_end
        if start_index < 0 or end_index < 0:
            raise RuntimeError("No se pudo ubicar el texto visible entre runs.")

        replacements: dict[int, str] = {}
        if start_index == end_index:
            value = nodes[start_index].group(2)
            replacements[start_index] = value[:start_offset] + replacement + value[end_offset:]
        else:
            first = nodes[start_index].group(2)
            last = nodes[end_index].group(2)
            replacements[start_index] = first[:start_offset] + replacement
            replacements[end_index] = last[end_offset:]
            for index in range(start_index + 1, end_index):
                replacements[index] = ""

        result = fragment
        for index in sorted(replacements, reverse=True):
            node = nodes[index]
            new_node = f"{node.group(1)}{replacements[index]}{node.group(3)}"
            result = result[: node.start()] + new_node + result[node.end() :]
        return result

    def add_gender_token(match: re.Match[str]) -> str:
        paragraph = match.group(1)
        if "{{BUYER_FULL_NAME}}" not in paragraph:
            return paragraph
        return replace_visible_text(paragraph, "identificada", "{{BUYER_IDENTIFIED_AS}}")

    xml = PARAGRAPH_PATTERN.sub(add_gender_token, xml)
    if "{{BUYER_IDENTIFIED_AS}}" not in xml:
        raise RuntimeError("No se insertó el token de concordancia de género.")

    def collapse_buyer_block(match: re.Match[str]) -> str:
        paragraph = match.group(1)
        if "{{BUYER_FULL_NAME}}" not in paragraph:
            return paragraph
        opening = re.match(r"<w:p(?:\s[^>]*)?>", paragraph)
        if opening is None:
            raise RuntimeError("No se pudo conservar el párrafo de compradores.")
        paragraph_properties = re.search(r"<w:pPr>.*?</w:pPr>", paragraph, re.DOTALL)
        properties = paragraph_properties.group(0) if paragraph_properties else ""
        return (
            f"{opening.group(0)}{properties}<w:r><w:rPr>"
            '<w:rFonts w:ascii="Century Schoolbook" w:hAnsi="Century Schoolbook"/>'
            '<w:sz w:val="20"/><w:szCs w:val="20"/>'
            "</w:rPr><w:t>{{BUYERS_BLOCK}}</w:t></w:r></w:p>"
        )

    xml = PARAGRAPH_PATTERN.sub(collapse_buyer_block, xml)
    if "{{BUYERS_BLOCK}}" not in xml:
        raise RuntimeError("No se preparó el bloque dinámico de compradores.")
    for token in BUYER_SOURCE_TOKENS:
        if token in xml:
            raise RuntimeError(f"El token singular {token} no fue absorbido por el bloque.")

    paragraphs = list(PARAGRAPH_PATTERN.finditer(xml))
    signature_line_index = next(
        (
            index
            for index, match in enumerate(paragraphs)
            if "--------------------------------------------" in match.group(1)
        ),
        -1,
    )
    if signature_line_index < 0 or signature_line_index + 1 >= len(paragraphs):
        raise RuntimeError("No se encontró el bloque original de firmas.")
    signature_label = paragraphs[signature_line_index + 1]
    if "EL VENDEDOR" not in signature_label.group(1):
        raise RuntimeError("El rótulo original de firmas cambió inesperadamente.")
    signature_start_index = signature_line_index
    while signature_start_index > 0 and signature_line_index - signature_start_index < 5:
        previous = paragraphs[signature_start_index - 1].group(1)
        visible = "".join(node.group(2) for node in TEXT_NODE_PATTERN.finditer(previous))
        if visible.strip():
            break
        signature_start_index -= 1
    signature_anchor = (
        '<w:p><w:pPr><w:spacing w:before="120" w:after="0"/>'
        '<w:jc w:val="center"/></w:pPr><w:r><w:t>'
        "{{SIGNATURES_BLOCK}}</w:t></w:r></w:p>"
    )
    start = paragraphs[signature_start_index].start()
    end = signature_label.end()
    xml = xml[:start] + signature_anchor + xml[end:]
    if xml.count("{{SIGNATURES_BLOCK}}") != 1:
        raise RuntimeError("No se preparó el bloque dinámico de firmas.")
    if PLACEHOLDER_PATTERN.search(xml):
        raise RuntimeError("Quedaron secuencias de X sin convertir en el documento.")
    return xml.encode("utf-8")


def prepare(source: Path, output: Path) -> None:
    if sha256(source) != EXPECTED_SOURCE_HASH:
        raise RuntimeError(
            "El DOCX fuente no coincide con la versión auditada; vuelve a destilar la plantilla."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source, "r") as original, zipfile.ZipFile(output, "w") as target:
        for item in original.infolist():
            data = original.read(item.filename)
            if item.filename == "word/document.xml":
                data = patch_document_xml(data)
            target.writestr(item, data)

    with zipfile.ZipFile(output, "r") as prepared:
        document_xml = prepared.read("word/document.xml").decode("utf-8")
        for token in TOKENS_IN_TEMPLATE:
            if document_xml.count(token) != 1:
                raise RuntimeError(f"El token {token} no aparece exactamente una vez.")
    print(f"Plantilla preparada: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara la plantilla semántica de la minuta.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    try:
        prepare(arguments.source.resolve(), arguments.output.resolve())
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
