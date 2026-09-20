from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin

from app.crawler.base import DiscoveredLink

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - optional dependency branch
    BeautifulSoup = None  # type: ignore[assignment]


@dataclass(slots=True)
class HtmlParseResult:
    title: str | None
    text: str
    markdown: str
    links: list[DiscoveredLink]


class HtmlContentParser:
    def parse(self, html: str, base_url: str) -> HtmlParseResult:
        if BeautifulSoup is not None:
            return self._parse_with_bs4(html, base_url)
        return self._parse_with_stdlib(html, base_url)

    def _parse_with_bs4(self, html: str, base_url: str) -> HtmlParseResult:
        soup = BeautifulSoup(html, "html.parser")
        for element in soup(["script", "style", "noscript"]):
            element.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else None
        links = [
            DiscoveredLink(url=urljoin(base_url, anchor.get("href", "")), text=anchor.get_text(" ", strip=True), source_url=base_url)
            for anchor in soup.find_all("a")
            if anchor.get("href")
        ]
        text = soup.get_text("\n", strip=True)
        markdown = "\n".join(line for line in text.splitlines() if line.strip())
        return HtmlParseResult(title=title, text=text, markdown=markdown, links=links)

    def _parse_with_stdlib(self, html: str, base_url: str) -> HtmlParseResult:
        parser = _StdlibHtmlParser(base_url)
        parser.feed(html)
        text = "\n".join(line.strip() for line in parser.text_parts if line.strip())
        return HtmlParseResult(title=parser.title, text=text, markdown=text, links=parser.links)


class _StdlibHtmlParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.text_parts: list[str] = []
        self.links: list[DiscoveredLink] = []
        self._current_href: str | None = None
        self._current_link_text: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []

    @property
    def title(self) -> str | None:
        value = " ".join(self._title_parts).strip()
        return value or None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "a" and attrs_dict.get("href"):
            self._current_href = attrs_dict["href"]
            self._current_link_text = []
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current_href:
            self.links.append(
                DiscoveredLink(
                    url=urljoin(self.base_url, self._current_href),
                    text=" ".join(self._current_link_text).strip(),
                    source_url=self.base_url,
                )
            )
            self._current_href = None
            self._current_link_text = []
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if not value:
            return
        self.text_parts.append(value)
        if self._current_href:
            self._current_link_text.append(value)
        if self._in_title:
            self._title_parts.append(value)
