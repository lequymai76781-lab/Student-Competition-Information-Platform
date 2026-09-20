"""Print cleaned text of saved official-evidence pages (offline recon tool).

Usage:
    python backend/scripts/v12_evidence_text_extract.py <file-or-dir> [<file-or-dir> ...]

HTML/JS pages are reduced to readable text. The script never writes files and
never touches the database; it is only used while building v12 evidence
registries from already-saved local snapshots.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


TAG_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)
STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.S | re.I)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
BR_RE = re.compile(r"<br\s*/?>|</(p|div|li|h\d|tr|td)>", re.I)
ANY_TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t\r\f\v]+")
BLANK_RE = re.compile(r"\n{3,}")


def clean_text(raw: bytes) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("gb18030", errors="replace")
    text = TAG_RE.sub(" ", text)
    text = STYLE_RE.sub(" ", text)
    text = COMMENT_RE.sub(" ", text)
    text = BR_RE.sub("\n", text)
    text = ANY_TAG_RE.sub("", text)
    text = html.unescape(text)
    lines = []
    for line in text.splitlines():
        line = WS_RE.sub(" ", line).strip()
        if line:
            lines.append(line)
    out = "\n".join(lines)
    out = BLANK_RE.sub("\n\n", out)
    return out


def pdf_text(path: Path) -> str:
    from app.crawler.parsers.pdf_parser import PdfParser

    parsed = PdfParser().parse(path)
    return parsed.text or f"[pdf text extraction failed: {parsed.error}]"


KEYWORDS = re.compile(
    r"主办|承办|指导|参赛|对象|报名|截止|总决赛|初赛|复赛|赛程|举办|章程|选手|团队|高校|2026|2025|2024"
)


def show(path: Path, *, max_chars: int = 14000, keyword_window: int = 2) -> None:
    print(f"\n======== {path} ({path.stat().st_size} bytes) ========")
    text = pdf_text(path) if path.suffix.lower() == ".pdf" else clean_text(path.read_bytes())
    if len(text) <= max_chars:
        print(text)
        return
    lines = text.splitlines()
    hits: set[int] = set()
    for idx, line in enumerate(lines):
        if KEYWORDS.search(line):
            for offset in range(-keyword_window, keyword_window + 1):
                target = idx + offset
                if 0 <= target < len(lines):
                    hits.add(target)
    printed = 0
    for idx in sorted(hits):
        if printed >= 120:
            print("... (more hits truncated)")
            break
        print(lines[idx])
        printed += 1


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    targets: list[Path] = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_dir():
            targets.extend(sorted(p.glob("*.html")))
            targets.extend(sorted(p.glob("*.htm")))
            targets.extend(sorted(p.glob("*.pdf")))
        else:
            targets.append(p)
    for target in targets:
        show(target)


if __name__ == "__main__":
    main()
