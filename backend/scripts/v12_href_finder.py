"""Print hrefs whose link text matches given keywords (offline recon tool)."""

from __future__ import annotations

import re
import sys
from html import unescape
from pathlib import Path


def main() -> None:
    file = Path(sys.argv[1])
    patterns = sys.argv[2:]
    raw = file.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("gb18030", errors="replace")
    anchors = re.findall(r"<a\b[^>]*href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", text, re.S | re.I)
    for href, inner in anchors:
        inner = unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        if not inner:
            continue
        if not patterns or any(keyword in inner for keyword in patterns):
            print(f"{inner}\n    -> {href}")


if __name__ == "__main__":
    main()
