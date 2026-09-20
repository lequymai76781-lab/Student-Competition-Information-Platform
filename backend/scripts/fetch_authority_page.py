"""Fetch one or more public authority pages / files and save them locally.

Usage:
    python backend/scripts/fetch_authority_page.py <url> <out_path> [<url> <out_path> ...]

Only saves the HTTP response bytes; no parsing or DB changes. Prints status,
content-type and final URL for each fetch so callers can verify provenance.
"""

import sys
import gzip
import os
import ssl
import urllib.request
from pathlib import Path


def fetch(url: str, out_path: Path) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    context = None
    if os.environ.get("FETCH_INSECURE") == "1":
        context = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=60, context=context) as resp:
        data = resp.read()
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            data = gzip.decompress(data)
        final_url = resp.geturl()
        content_type = resp.headers.get("Content-Type", "")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    return {
        "url": url,
        "final_url": final_url,
        "content_type": content_type,
        "size": len(data),
        "out_path": str(out_path),
    }


def main() -> None:
    pairs = sys.argv[1:]
    if len(pairs) % 2 != 0:
        raise SystemExit("usage: fetch_authority_page.py <url> <out_path> [<url> <out_path> ...]")
    for index in range(0, len(pairs), 2):
        url, out = pairs[index], pairs[index + 1]
        result = fetch(url, Path(out))
        print(f"{result['final_url']}\t{result['content_type']}\t{result['size']}\t{result['out_path']}")


if __name__ == "__main__":
    main()
