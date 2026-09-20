from pathlib import Path

from app.crawler.parsers.pdf_parser import ParsedDocument


class TableParser:
    def parse_text_table(self, text: str) -> list[list[str]]:
        rows: list[list[str]] = []
        for line in text.splitlines():
            if "\t" in line:
                rows.append([cell.strip() for cell in line.split("\t")])
            elif "," in line:
                rows.append([cell.strip() for cell in line.split(",")])
        return rows

    def parse(self, path: Path) -> ParsedDocument:
        try:
            return ParsedDocument(text=path.read_text(encoding="utf-8"), parser_type="text-table")
        except UnicodeDecodeError:
            return ParsedDocument(text=path.read_text(encoding="gb18030", errors="ignore"), parser_type="text-table")
