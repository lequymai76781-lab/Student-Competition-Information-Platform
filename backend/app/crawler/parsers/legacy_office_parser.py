from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.crawler.parsers.pdf_parser import ParsedDocument


class LegacyWordParser:
    """Parse binary DOC when antiword is available; otherwise fail explicitly."""

    def parse(self, path: Path) -> ParsedDocument:
        executable = shutil.which("antiword")
        if not executable:
            return ParsedDocument(
                text="",
                parser_type="antiword",
                error="Legacy DOC downloaded but antiword is unavailable",
            )
        try:
            result = subprocess.run(
                [executable, str(path)],
                capture_output=True,
                check=False,
                timeout=30,
            )
            if result.returncode:
                return ParsedDocument(text="", parser_type="antiword", error=result.stderr.decode("utf-8", "ignore"))
            text = result.stdout.decode("utf-8", "ignore") or result.stdout.decode("gb18030", "ignore")
            return ParsedDocument(text=text, parser_type="antiword")
        except (OSError, subprocess.SubprocessError) as exc:
            return ParsedDocument(text="", parser_type="antiword", error=str(exc))


class LegacyExcelParser:
    def parse(self, path: Path) -> ParsedDocument:
        try:
            import xlrd
        except ImportError:
            return ParsedDocument(text="", parser_type="xlrd", error="Missing XLS parser dependency: xlrd")
        try:
            workbook = xlrd.open_workbook(str(path))
            lines: list[str] = []
            for sheet in workbook.sheets():
                lines.append(f"# {sheet.name}")
                for row_index in range(sheet.nrows):
                    values = [str(value).strip() for value in sheet.row_values(row_index) if str(value).strip()]
                    if values:
                        lines.append("\t".join(values))
            return ParsedDocument(text="\n".join(lines), parser_type="xlrd")
        except Exception as exc:  # xlrd exposes multiple format-specific exceptions
            return ParsedDocument(text="", parser_type="xlrd", error=str(exc))
