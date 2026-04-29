"""External catalog page fetching."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

import httpx


@dataclass(frozen=True)
class FetchedExternalPage:
    url: str
    final_url: str
    title: str | None
    text: str
    status_code: int
    content_type: str | None


class HttpExternalPageFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        max_bytes: int = 1_048_576,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    async def fetch_page(self, *, url: str, payload: dict[str, Any]) -> FetchedExternalPage:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout_seconds,
            headers={"User-Agent": "pur-leads-catalog-fetcher/1.0"},
        ) as client:
            response = await client.get(url)
        response.raise_for_status()
        content = response.content
        if len(content) > self.max_bytes:
            raise ValueError("external page exceeds configured max bytes")
        content_type = response.headers.get("content-type")
        text, title = _extract_page_text(content, content_type=content_type, fallback=response.text)
        if not text.strip():
            raise ValueError("external page has no readable text")
        return FetchedExternalPage(
            url=url,
            final_url=str(response.url),
            title=title,
            text=text,
            status_code=response.status_code,
            content_type=content_type,
        )


class _ReadableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []

    @property
    def title(self) -> str | None:
        title = " ".join(" ".join(self._title_parts).split())
        return title or None

    @property
    def text(self) -> str:
        return " ".join(" ".join(self._text_parts).split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in {"p", "div", "section", "article", "br", "li", "h1", "h2", "h3"}:
            self._text_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3"}:
            self._text_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        self._text_parts.append(data)


def _extract_page_text(
    content: bytes,
    *,
    content_type: str | None,
    fallback: str,
) -> tuple[str, str | None]:
    if content_type is not None and "html" not in content_type.lower():
        return " ".join(fallback.split()), None
    parser = _ReadableHtmlParser()
    parser.feed(fallback)
    return parser.text, parser.title
