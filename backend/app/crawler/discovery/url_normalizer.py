from __future__ import annotations

import posixpath
from html import unescape
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit


class OfficialUrlNormalizer:
    """Canonicalize official-site URLs while preserving download queries."""

    tracking_parameters = {
        "from", "spm", "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term",
    }

    def normalize(self, url: str, *, base_url: str | None = None) -> str:
        value = unescape((url or "").strip()).replace("\\/", "/")
        if not value or value.startswith(("javascript:", "mailto:", "tel:", "#")):
            return ""
        if base_url:
            value = urljoin(base_url, value)
        elif value.startswith("//"):
            value = f"https:{value}"
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return ""
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname.lower().rstrip(".")
        port = parsed.port
        netloc = hostname
        if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
            netloc = f"{hostname}:{port}"
        raw_path = parsed.path or "/"
        had_trailing_slash = raw_path.endswith("/")
        path = posixpath.normpath(raw_path)
        if not path.startswith("/"):
            path = f"/{path}"
        if had_trailing_slash and path != "/":
            path = f"{path}/"
        path = quote(path, safe="/%:@!$&'()*+,;=-._~")
        query_items = [
            (key, item_value)
            for key, item_value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in self.tracking_parameters
        ]
        query_items.sort(key=lambda item: (item[0].lower(), item[1]))
        return urlunsplit((scheme, netloc, path, urlencode(query_items, doseq=True), ""))

    def is_official(self, url: str, official_domain: str) -> bool:
        normalized = self.normalize(url)
        if not normalized:
            return False
        host = (urlsplit(normalized).hostname or "").lower().removeprefix("www.")
        domain = official_domain.lower().split(":", 1)[0].removeprefix("www.").rstrip(".")
        return host == domain or host.endswith(f".{domain}")
