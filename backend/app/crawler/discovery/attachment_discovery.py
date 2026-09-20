import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from app.crawler.base import AttachmentCandidate, DiscoveredLink


class AttachmentDiscoveryService:
    extensions = {".pdf", ".doc", ".docx", ".xls", ".xlsx"}
    endpoint_markers = (
        "attachment",
        "download",
        "upload",
        "/file/",
        "/files/",
        "system/_content",
        "__local",
        "/_upload/",
        "downloadattachurl",
        "wbfileid=",
    )

    def discover(self, links: list[DiscoveredLink]) -> list[AttachmentCandidate]:
        attachments: list[AttachmentCandidate] = []
        seen: set[str] = set()
        for link in links:
            extension = self.detect_extension(link.url, link.text)
            looks_like_endpoint = any(marker in link.url.lower() for marker in self.endpoint_markers)
            looks_like_attachment = bool(extension) or looks_like_endpoint or "附件" in link.text
            if not looks_like_attachment or link.url in seen:
                continue
            seen.add(link.url)
            attachments.append(
                AttachmentCandidate(
                    url=link.url,
                    filename=self._filename(link.url, link.text, extension),
                    extension=extension.lstrip(".") if extension else None,
                    source_url=link.source_url,
                    link_text=link.text,
                )
            )
        return attachments

    def detect_extension(self, url: str, link_text: str = "") -> str:
        parsed = urlparse(unquote(url))
        candidates = [parsed.path, link_text]
        for values in parse_qs(parsed.query).values():
            candidates.extend(values)
        candidates.append(parsed.query)
        for value in candidates:
            matches = re.findall(r"(?i)(\.pdf|\.docx?|\.xlsx?)(?:$|[^a-z0-9])", value or "")
            if matches:
                return matches[-1].lower()
        return ""

    def _filename(self, url: str, link_text: str, extension: str) -> str | None:
        path_name = Path(unquote(urlparse(url).path)).name
        if path_name and "." in path_name:
            return path_name
        text = " ".join((link_text or "").split()).strip("：: 〖〗[]【】")
        if text:
            if extension and not text.lower().endswith(extension):
                return f"{text}{extension}"
            return text
        return None