from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ParsedDocument:
    text: str
    parser_type: str
    page_count: int | None = None
    needs_ocr: bool = False
    error: str | None = None


class PdfParser:
    def parse(self, path: Path) -> ParsedDocument:
        try:
            import fitz
        except ImportError:
            fitz = None  # type: ignore[assignment]

        if fitz is not None:
            try:
                document = fitz.open(path)
                parts = [page.get_text("text") for page in document]
                text = "\n".join(part.strip() for part in parts if part and part.strip())
                return ParsedDocument(text=text, parser_type="pymupdf", page_count=document.page_count, needs_ocr=not bool(text))
            except Exception as exc:
                return ParsedDocument(text="", parser_type="pymupdf", error=str(exc))

        try:
            import pdfplumber
        except ImportError:
            return ParsedDocument(text="", parser_type="pdf", error="Missing PDF parser dependency: PyMuPDF or pdfplumber")

        try:
            with pdfplumber.open(path) as pdf:
                parts = [page.extract_text() or "" for page in pdf.pages]
            text = "\n".join(part.strip() for part in parts if part.strip())
            return ParsedDocument(text=text, parser_type="pdfplumber", page_count=len(parts), needs_ocr=not bool(text))
        except Exception as exc:
            return ParsedDocument(text="", parser_type="pdfplumber", error=str(exc))
