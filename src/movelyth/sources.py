"""Read-only source evidence snapshots; remote text is always treated as data."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .util import atomic_json, fingerprint, now, read_json


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ignored = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "nav"}:
            self.ignored += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "svg", "nav"}:
            self.ignored = max(0, self.ignored - 1)

    def handle_data(self, data):
        if not self.ignored and data.strip():
            self.parts.append(data.strip())


def collect_sources(sources: list[dict], directory: Path) -> list[dict]:
    directory.mkdir(parents=True, exist_ok=True)
    result = []
    for source in sources:
        url = source["url"]
        cached = directory / (fingerprint(url)[:20] + ".json")
        if cached.exists():
            result.append(read_json(cached))
            continue
        item = {**source, "retrieved_at": now()}
        try:
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.username or parsed.password or not parsed.hostname:
                raise ValueError("仅获取无凭据的 HTTPS 来源")
            request = Request(url, headers={"User-Agent": "Movelyth/0.1 source-verification"})
            with urlopen(request, timeout=20) as response:
                final = response.geturl()
                if urlparse(final).scheme != "https":
                    raise ValueError("来源重定向至非 HTTPS")
                raw = response.read(1_500_001)
                if len(raw) > 1_500_000:
                    raise ValueError("来源正文超出读取上限")
                encoding = response.headers.get_content_charset() or "utf-8"
                parser = ArticleText()
                parser.feed(raw.decode(encoding, errors="replace"))
                text = " ".join(parser.parts)
                if len(text) < 100:
                    raise ValueError("来源没有足够可提取正文")
                item.update({"status": "retrieved", "resolved_url": final,
                             "content_sha256": hashlib.sha256(raw).hexdigest(), "excerpt": text[:16000]})
        except Exception as exc:
            item.update({"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"})
        atomic_json(cached, item)
        result.append(item)
    return result
