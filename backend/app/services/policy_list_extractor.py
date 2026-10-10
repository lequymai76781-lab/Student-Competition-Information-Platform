"""Conservative, evidence-preserving extraction of competition names from policy lists."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from app.crawler.parsers.docx_parser import DocxParser
from app.crawler.parsers.excel_parser import ExcelParser
from app.crawler.parsers.legacy_office_parser import LegacyExcelParser, LegacyWordParser
from app.crawler.parsers.pdf_parser import PdfParser


_PARSERS = {
    ".pdf": PdfParser,
    ".docx": DocxParser,
    ".xlsx": ExcelParser,
    ".doc": LegacyWordParser,
    ".xls": LegacyExcelParser,
}
_EXCLUDED = re.compile(r"(?:不予|不纳入|不包括|排除|除外|不认定|不得认定|未列入|仅供参考|不计入|不计分|不加分)")
_HEADER = re.compile(r"^(?:序号|编号|竞赛名称|赛事名称|比赛名称|项目名称|级别|类别|等级|认定范围|名单|附件|备注|获奖等级)$")
_COMPETITION = re.compile(r"(?:竞赛|大赛|比赛|挑战赛|联赛|专项赛|赛道|杯|奥林匹克|ACM|ICPC|MCM|COMAP)", re.I)
_NUMBER = re.compile(r"^\s*(?:(?:\d{1,3}|[一二三四五六七八九十]{1,3})[.、．)）]|\(\d{1,3}\)|（\d{1,3}）)\s*")
_CATEGORY = re.compile(r"[（(]\s*(?:[A-D一二三四五六甲乙丙丁]类|国家级|省级|校级|认定)\s*[）)]\s*$")
_CLASS_PREFIX = re.compile(r"^\s*(?:[A-Da-d一二三四五六甲乙丙丁]类|国家级|省级|校级)\s*[:：、.．-]?\s*")
_SECTION_NUMBER = re.compile(r"^\s*(?:[一二三四五六七八九十]+[、.．]|第[一二三四五六七八九十\d]+[章节]|附件[一二三四五六七八九十\d]+[:：]?|附表[一二三四五六七八九十\d]+[:：]?)")
_SECTION_TOPIC = re.compile(r"(?:认定|认可|纳入|参考|排除|奖励|加分|学分|测评|名单|目录|范围|说明|赛事|竞赛|比赛)")
_INCLUDED = re.compile(r"(?:认定|认可|纳入|计入|奖励|加分|学分|测评|正式赛事|有效赛事)")
_NAME_HEADER = re.compile(r"^(?:竞赛|赛事|比赛|项目|竞)(?:项目)?名称$|^competitionname$", re.I)
_CONTEXT_HEADER = re.compile(r"(?:用途|类型|类别|政策|奖励|加分|认定|状态|备注)")
_STATUS_HEADER = re.compile(r"(?:是否|状态|备注|用途|认定)")
_NEGATIVE_CELL = re.compile(r"(?:^否$|未认定|不认定|不予认定|不纳入|未纳入|不计分|不加分|不适用|仅供参考|^参考$|^无$)")
_SERIAL_CELL = re.compile(r"\d{1,3}(?:\.0)?")


class _PolicyHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[str, str]] = []
        self._tag: str | None = None
        self._parts: list[str] = []
        self._cells: list[str] = []
        self._in_table = False
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "table":
            self._in_table = True
            self.rows.append(("table_start", ""))
        if tag == "tr":
            self._cells = []
        if tag in {"td", "th", "li", "p", "h1", "h2", "h3", "h4", "h5", "h6"} and self._tag is None:
            self._tag = tag
            self._parts = []
        if tag == "br" and self._tag:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._tag and not self._skip:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1
            return
        if self._skip:
            return
        if tag == self._tag:
            value = "".join(self._parts).strip()
            if tag in {"td", "th"}:
                self._cells.append(value)
            elif value:
                self.rows.append(("heading" if tag.startswith("h") else tag, value))
            self._tag = None
            self._parts = []
        if tag == "tr" and self._cells:
            self.rows.append(("tr", "\t".join(self._cells)))
            self._cells = []
        if tag == "table":
            self._in_table = False
            self.rows.append(("table_end", ""))


def _clean_name(value: str) -> str:
    value = _NUMBER.sub("", value.strip())
    value = _CLASS_PREFIX.sub("", value)
    value = re.sub(r"^(?:竞赛名称|赛事名称|比赛名称|项目名称)\s*[:：]\s*", "", value)
    value = _CATEGORY.sub("", value).strip(" \t\u3000，,；;。:：")
    return value


def _valid_name(value: str, *, listed: bool = False) -> bool:
    if not value or _HEADER.fullmatch(value) or _EXCLUDED.search(value):
        return False
    if len(value) > 120 or len(value) < 3:
        return False
    if re.search(r"(?:通知|请各|提交|附件下载|公示|规定|按照|根据|包含以下|包括以下)", value):
        return False
    return bool(_COMPETITION.search(value)) or listed


def _pieces(line: str, *, kind: str, name_column: int | None) -> list[str]:
    if _EXCLUDED.search(line):
        return []
    if kind == "tr" or "\t" in line:
        cells = [cell.strip() for cell in line.split("\t")]
        if name_column is not None and name_column < len(cells):
            column = name_column + (1 if _SERIAL_CELL.fullmatch(cells[0]) and name_column == 0 else 0)
            return [cells[column]] if column < len(cells) else []
        possible = [cell for cell in cells if _valid_name(_clean_name(cell))]
        return possible if len(possible) == 1 else []
    match = re.search(r"(?:竞赛|赛事|比赛)(?:名单)?(?:包括|包含|有|为)\s*[:：]", line)
    if match:
        return re.split(r"[、，,；;]", line[match.end():])
    if kind == "li" or _NUMBER.match(line) or _CLASS_PREFIX.match(line):
        return [line]
    return []


def _is_heading(kind: str, line: str) -> bool:
    if kind == "heading":
        return True
    if kind == "tr" and "\t" not in line and len(line) <= 65:
        return bool((_EXCLUDED.search(line) or _INCLUDED.search(line))
                    and re.search(r"(?:赛事|竞赛|比赛|名单|目录|范围|项目|参考)$", line))
    if kind not in {"line", "p"} or len(line) > 65 or "\t" in line or line.endswith(("。", ".", "；", ";")):
        return False
    if (re.match(r"^(?:以下|下列)(?:竞赛|赛事|比赛)", line)
            and (_EXCLUDED.search(line) or _INCLUDED.search(line))
            and re.search(r"(?:范围|目录|名单|赛事|竞赛|比赛)[:：]?$", line)):
        return True
    if _SECTION_NUMBER.match(line):
        return bool(_SECTION_TOPIC.search(line))
    if _INCLUDED.search(line) and re.search(r"(?:目录|名单|范围|清单|类别|赛事)$", line):
        return True
    return bool(re.match(r"^(?:不予认定|不纳入|仅供参考|参考赛事|排除赛事)", line)
                and (_SECTION_TOPIC.search(line) or line == "仅供参考"))


def _table_header(line: str) -> tuple[int, list[str]] | None:
    if "\t" not in line:
        return None
    cells = [cell.strip() for cell in line.split("\t")]
    name_index = next((index for index, cell in enumerate(cells)
                       if _NAME_HEADER.fullmatch(re.sub(r"\s+", "", cell))), None)
    return (name_index, cells) if name_index is not None else None


def _table_context(line: str, headers: list[str], name_column: int) -> tuple[dict[str, str], bool]:
    cells = [cell.strip() for cell in line.split("\t")]
    # Text extracted from a PDF can add a serial cell that was absent from its header.
    offset = 1 if name_column == 0 and cells and _SERIAL_CELL.fullmatch(cells[0]) else 0
    context: dict[str, str] = {}
    rejected = False
    for index, header in enumerate(headers):
        cell_index = index + offset
        if index == name_column or cell_index >= len(cells) or not _CONTEXT_HEADER.search(header):
            continue
        value = cells[cell_index]
        if value:
            context[header] = value
            if _STATUS_HEADER.search(header) and _NEGATIVE_CELL.search(value):
                rejected = True
    return context, rejected


def analyze_policy_content(content: str, *, format: str = "text", title: str = "") -> dict:
    """Return entries and conservative diagnostics for stored policy text."""
    if not content or not content.strip():
        return {"entries": [], "extraction_complete": False, "extraction_warnings": ["no_text"]}
    if format.lower() in {"html", "htm"}:
        parser = _PolicyHTML()
        parser.feed(content)
        source_rows = parser.rows
    else:
        source_rows = [("line", line) for line in content.splitlines()]

    entries: list[dict] = []
    warnings: list[str] = []
    name_column: int | None = None
    headers: list[str] = []
    section_heading: str | None = None
    excluded_section = False
    index = 0
    while index < len(source_rows):
        kind, line = source_rows[index]
        source_line = index + 1
        line = line.strip()
        if kind in {"table_start", "table_end"}:
            name_column = None
            headers = []
            index += 1
            continue
        if not line:
            index += 1
            continue
        if _is_heading(kind, line):
            section_heading = line
            name_column = None
            headers = []
            if _EXCLUDED.search(line) or re.search(r"(?:参考|排除)(?:赛事|竞赛|比赛|名单|目录)", line):
                excluded_section = True
            elif _INCLUDED.search(line):
                excluded_section = False
            index += 1
            continue
        header = _table_header(line)
        if header is not None:
            name_column, headers = header
            index += 1
            continue
        if excluded_section:
            index += 1
            continue
        evidence = line
        if kind == "line" and format.lower() == "pdf" and index + 1 < len(source_rows):
            next_line = source_rows[index + 1][1].strip()
            # PDF text extraction often wraps one table cell across physical lines.
            current_pieces = _pieces(line, kind=kind, name_column=name_column)
            next_has_category = bool(re.search(r"\t\s*(?:[A-Da-d一二三四五六甲乙丙丁]类|国家级|省级|校级)\s*$", next_line))
            if ("\t" in line and current_pieces
                    and (not _valid_name(_clean_name(current_pieces[0])) or next_has_category)
                    and not re.match(r"^\d{1,3}\s*\t", next_line)
                    and not _EXCLUDED.search(next_line)
                    and _COMPETITION.search(next_line)):
                prefix, suffix = line.rsplit("\t", 1)
                continuation, _, trailing = next_line.partition("\t")
                line = prefix + "\t" + suffix + continuation + ("\t" + trailing if trailing else "")
                evidence = source_rows[index][1].strip() + "\n" + next_line
                index += 1
        benefit_context: dict[str, str] = {}
        if headers and name_column is not None and "\t" in line:
            benefit_context, rejected = _table_context(line, headers, name_column)
            if rejected:
                index += 1
                continue
        extracted = False
        for piece in _pieces(line, kind=kind, name_column=name_column):
            name = _clean_name(piece.replace("\n", ""))
            if _valid_name(name, listed=name_column is not None):
                entries.append({
                    "raw_competition_name": name,
                    "evidence_text": evidence,
                    "locator": f"{'row' if kind == 'tr' else 'line'}:{source_line}",
                    "section_heading": section_heading,
                    "benefit_context": benefit_context.copy(),
                })
                extracted = True
        if (not extracted and _COMPETITION.search(line) and not _EXCLUDED.search(line)
                and (re.match(r"^\s*[①②③④⑤⑥⑦⑧⑨⑩]", line) or "\t" in line
                     or (kind == "tr" and name_column is not None))):
            warnings.append(f"unparsed_competition_{'row' if kind == 'tr' else 'line'}:{source_line}")
        index += 1
    if not entries:
        warnings.append("no_entries")
    return {"entries": entries, "extraction_complete": not warnings, "extraction_warnings": warnings}


def extract_policy_entries(content: str, *, format: str = "text", title: str = "") -> list[dict]:
    """Extract explicitly listed names; every result retains source and scope."""
    return analyze_policy_content(content, format=format, title=title)["entries"]


def _flatten_pdf_cell(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"(?<=[A-Za-z0-9])\n(?=[A-Za-z0-9])", " ", text)
    return text.replace("\n", "").replace("\t", " ").strip()


def _pdf_table_content(path: Path) -> tuple[str, list[str], list[str]] | None:
    """Place detected table rows among page text blocks so heading scope is retained."""
    try:
        import fitz
    except ImportError:
        return None
    try:
        document = fitz.open(path)
    except Exception:
        return None  # The repository PDF parser supplies the authoritative error.
    lines: list[str] = []
    locators: list[str] = []
    warnings: list[str] = []
    found_table = False
    carried_header: list[str] | None = None
    last_serial: int | None = None
    try:
        for page_number, page in enumerate(document, 1):
            try:
                tables = list(page.find_tables().tables)
            except Exception:
                warnings.append(f"pdf_table_detection_failed:page:{page_number}")
                tables = []
            found_table |= bool(tables)
            table_rects = [fitz.Rect(table.bbox) for table in tables]
            events: list[tuple[float, float, str, object, int]] = []
            for table_number, table in enumerate(tables, 1):
                rows = list(table.extract())
                first = "\t".join(_flatten_pdf_cell(cell) for cell in rows[0]) if rows else ""
                identified = _table_header(first)
                if identified is not None:
                    carried_header = [_flatten_pdf_cell(cell) for cell in rows[0]]
                else:
                    first_serial = next((int(str(row[0]).strip()) for row in rows
                                         if row and str(row[0] or "").strip().isdigit()), None)
                    if (carried_header is not None and rows and len(rows[0]) == len(carried_header)
                            and last_serial is not None and first_serial == last_serial + 1):
                        rows = [carried_header] + rows
                    else:
                        warnings.append(f"pdf_table_without_name_header:page:{page_number}/table:{table_number}")
                        carried_header = None
                        last_serial = None
                        continue
                serials = [int(str(row[0]).strip()) for row in rows
                           if row and str(row[0] or "").strip().isdigit()]
                if serials:
                    last_serial = max(serials)
                events.append((table.bbox[1], table.bbox[0], "table", rows, table_number))
            for block_number, block in enumerate(page.get_text("blocks"), 1):
                if len(block) < 7 or block[6] != 0 or not str(block[4]).strip():
                    continue
                rect = fitz.Rect(block[:4])
                overlapping = [table_rect for table_rect in table_rects if rect.intersects(table_rect)]
                if overlapping:
                    if any(rect.y0 < table_rect.y0 - 1 or rect.y1 > table_rect.y1 + 1 for table_rect in overlapping):
                        warning = f"pdf_table_context_overlap:page:{page_number}"
                        if warning not in warnings:
                            warnings.append(warning)
                    continue
                events.append((rect.y0, rect.x0, "text", str(block[4]), block_number))
            for _, _, kind, value, number in sorted(events, key=lambda item: (item[0], item[1])):
                if kind == "table":
                    for row_number, row in enumerate(value, 1):
                        line = "\t".join(_flatten_pdf_cell(cell) for cell in row)
                        if line.strip("\t "):
                            lines.append(line)
                            locators.append(f"page:{page_number}/table:{number}/row:{row_number}")
                else:
                    for text_line_number, line in enumerate(value.splitlines(), 1):
                        if line.strip():
                            lines.append(line.strip())
                            locators.append(f"page:{page_number}/block:{number}/line:{text_line_number}")
            if not page.get_text("text").strip():
                warnings.append(f"pdf_page_no_text:page:{page_number}")
    finally:
        document.close()
    return ("\n".join(lines), locators, warnings) if found_table else None


def parse_policy_file(path: str | Path) -> dict:
    """Use repository parsers without OCR, network access, or inferred names."""
    path = Path(path)
    result = {
        "content_text": "", "entries": [], "needs_ocr": False, "error": None, "parser_type": None,
        "extraction_complete": False, "extraction_warnings": [],
    }
    if not path.is_file():
        result["error"] = f"Policy file not found: {path}"
        return result
    suffix = path.suffix.lower()
    parser_class = _PARSERS.get(suffix)
    if parser_class is None and suffix not in {".html", ".htm", ".txt"}:
        result["error"] = f"Unsupported policy file format: {suffix or '(none)'}"
        return result
    if parser_class:
        parsed = parser_class().parse(path)
        result.update(content_text=parsed.text, needs_ocr=parsed.needs_ocr, error=parsed.error, parser_type=parsed.parser_type)
    else:
        try:
            result["content_text"] = path.read_text(encoding="utf-8-sig")
            result["parser_type"] = "html" if suffix in {".html", ".htm"} else "text"
        except UnicodeDecodeError:
            result["content_text"] = path.read_text(encoding="gb18030", errors="replace")
            result["parser_type"] = "html" if suffix in {".html", ".htm"} else "text"
        except OSError as exc:
            result["error"] = str(exc)
    if result["content_text"] and not result["error"]:
        pdf_table_result = _pdf_table_content(path) if suffix == ".pdf" else None
        if pdf_table_result is not None:
            table_text, locators, table_warnings = pdf_table_result
            analyzed = analyze_policy_content(table_text, format="text")
            for entry in analyzed["entries"]:
                source_line = int(entry["locator"].split(":")[-1])
                entry["locator"] = locators[source_line - 1]
            non_table_entries = [entry for entry in analyzed["entries"] if "/table:" not in entry["locator"]]
            analyzed["entries"] = [entry for entry in analyzed["entries"] if "/table:" in entry["locator"]]
            if non_table_entries:
                analyzed["extraction_warnings"].append("pdf_non_table_candidates_ignored")
            if not analyzed["entries"] and "no_entries" not in analyzed["extraction_warnings"]:
                analyzed["extraction_warnings"].append("no_entries")
            analyzed["extraction_warnings"].extend(table_warnings)
            analyzed["extraction_complete"] = not analyzed["extraction_warnings"]
            result.update(analyzed)
        else:
            result.update(analyze_policy_content(result["content_text"], format=suffix.lstrip(".")))
    elif not result["error"] and not result["needs_ocr"]:
        result["error"] = "No extractable text in policy file"
    return result
