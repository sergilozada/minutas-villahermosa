"""Package the existing Python DOCX engine for offline browser execution."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "static" / "engine.zip"
FILES = (
    "backend/__init__.py",
    "backend/config.py",
    "backend/schema.py",
    "backend/document_engine.py",
    "config/minute_schema.json",
    "templates/minuta_financiado_template.docx",
    "static/assets/ayt-house-logo.png",
    "static/assets/villa-hermosa-wordmark.png",
)


def main() -> None:
    with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as package:
        for relative_path in FILES:
            source = ROOT / relative_path
            if not source.is_file():
                raise FileNotFoundError(source)
            package.write(source, relative_path)
    print(f"Packaged {len(FILES)} engine assets: {OUTPUT}")


if __name__ == "__main__":
    main()
