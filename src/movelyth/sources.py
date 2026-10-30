"""Read-only source evidence snapshots with SSRF protection.

Remote text is always treated as data.  Fetching is pinned to a validated
public IP so DNS rebinding cannot redirect a request to loopback, private or
metadata addresses; redirects are re-validated hop by hop.
"""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import socket
import ssl
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .util import atomic_json, fingerprint, now, read_json

MAX_URL = 2000
MAX_BYTES = 1_500_000
MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 20
SUCCESS_TTL = timedelta(days=30)
FAILURE_TTL = timedelta(hours=6)
ALLOWED_MIME = {"text/html", "text/plain", "application/xhtml+xml", "application/xml", "text/xml"}
BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "metadata.azure.internal"}
BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa", ".lan")


class BlockedSource(ValueError):
    """The URL or resolved address is outside the allowed public surface."""


class SourceError(RuntimeError):
    """A remote source failed for an ordinary reason (HTTP error, missing body)."""


class ArticleText(HTMLParser):
    """Extract visible text and the document title; script/style bodies are ignored."""

    def __init__(self):
        super().__init__()
        self.ignored = 0
        self.parts = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "nav", "iframe", "noscript"}:
            self.ignored += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "svg", "nav", "iframe", "noscript"}:
            self.ignored = max(0, self.ignored - 1)
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title + " " + data.strip()).strip()
            return
        if not self.ignored and data.strip():
            self.parts.append(data.strip())


def _public_address(ip: str) -> str:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError as exc:
        raise BlockedSource(f"无法解析的地址：{ip}") from exc
    if not address.is_global or address.is_multicast or address.is_reserved:
        raise BlockedSource(f"来源地址不属于公网：{ip}")
    return str(address)


def validate_url(url: str) -> str:
    """Structural validation before any DNS lookup happens."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL:
        raise BlockedSource("来源 URL 为空或过长")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise BlockedSource("仅允许 HTTPS 来源")
    if parsed.username or parsed.password:
        raise BlockedSource("来源 URL 不得包含凭据")
    if parsed.port not in (None, 443):
        raise BlockedSource("仅允许 443 端口")
    host = (parsed.hostname or "").strip(".").lower()
    if not host or len(host) > 253:
        raise BlockedSource("来源主机名无效")
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_SUFFIXES):
        raise BlockedSource(f"来源主机名被禁止：{host}")
    if not parsed.path.startswith("/"):
        raise BlockedSource("来源路径无效")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        _public_address(str(literal))
    return host


def resolve_public(host: str, *, resolver=None) -> list[str]:
    """Resolve a hostname and reject the request if *any* answer is non-public."""
    try:
        ipaddress.ip_address(host)
        return [_public_address(host)]
    except ValueError:
        pass
    try:
        answers = (resolver or socket.getaddrinfo)(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise BlockedSource(f"DNS 解析失败：{exc}") from exc
    addresses = sorted({_public_address(answer[4][0]) for answer in answers})
    if not addresses:
        raise BlockedSource("DNS 未返回任何地址")
    return addresses


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a validated IP while keeping TLS SNI/Host for the real hostname."""

    def __init__(self, host: str, ip: str, timeout: float):
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _open_pinned(host: str, ip: str, timeout: float):
    return _PinnedHTTPSConnection(host, ip, timeout)


def _read_response(response) -> tuple[int, dict, bytes]:
    status = response.status
    headers = {key.lower(): value for key, value in response.getheaders()}
    raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise BlockedSource("来源正文超出读取上限")
    return status, headers, raw


def fetch_document(url: str, *, resolver=None, opener=None) -> dict:
    """Fetch one HTTPS document through validated IPs, following bounded redirects."""
    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        host = validate_url(current)
        addresses = resolve_public(host, resolver=resolver)
        parsed = urlparse(current)
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        addresses = addresses[:4]  # Bound worst-case connection time per redirect.
        for ip in addresses:
            connection = None
            try:
                connection = (opener or _open_pinned)(host, ip, TIMEOUT_SECONDS)
                connection.request("GET", path, headers={
                    "User-Agent": "Movelyth/1.0 source-verification",
                    "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                })
                status, headers, raw = _read_response(connection.getresponse())
                break
            except (OSError, http.client.HTTPException):
                if ip == addresses[-1]:
                    raise
            finally:
                if connection is not None:
                    connection.close()
        if status in {301, 302, 303, 307, 308}:
            location = headers.get("location")
            if not location:
                raise SourceError("重定向缺少 Location")
            current = urljoin(current, location)
            continue
        if not 200 <= status < 300:
            raise SourceError(f"来源返回 HTTP {status}")
        mime = (headers.get("content-type") or "").split(";")[0].strip().lower()
        if mime and mime not in ALLOWED_MIME:
            raise BlockedSource(f"不支持的来源类型：{mime}")
        charset = "utf-8"
        for part in (headers.get("content-type") or "").split(";")[1:]:
            if "charset=" in part:
                charset = part.split("=", 1)[1].strip().strip('"') or "utf-8"
        return {"final_url": current, "resolved_ip": ip, "status_code": status,
                "content_type": mime or "text/html", "charset": charset, "raw": raw}
    raise SourceError("重定向次数过多")


def _age(record: dict) -> timedelta | None:
    try:
        stamp = datetime.fromisoformat(record["retrieved_at"])
    except (KeyError, TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - stamp


def _cache_valid(record: dict) -> bool:
    age = _age(record)
    if age is None:
        return False
    # Older successful snapshots kept only a prefix and cannot prove an excerpt
    # is absent from the rest of a document. Refresh them before using them.
    if record.get("status") == "retrieved" and "search_text" not in record:
        return False
    ttl = SUCCESS_TTL if record.get("status") == "retrieved" else FAILURE_TTL
    return age < ttl


def collect_sources(sources: list[dict], directory: Path, *, resolver=None, opener=None) -> list[dict]:
    """Cache evidence with explicit states and short-lived failure records."""
    directory.mkdir(parents=True, exist_ok=True)
    result = []
    for source in sources:
        url = source["url"]
        cached = directory / (fingerprint(url)[:20] + ".json")
        if cached.exists():
            try:
                record = read_json(cached)
            except (OSError, ValueError):
                record = None
            if record and _cache_valid(record):
                result.append({**record, "cache_state": "fresh"})
                continue
        item = {**source, "retrieved_at": now(), "cache_state": "fetched"}
        try:
            document = fetch_document(url, resolver=resolver, opener=opener)
            parser = ArticleText()
            parser.feed(document["raw"].decode(document["charset"], errors="replace"))
            text = " ".join(parser.parts)
            if len(text) < 100:
                raise BlockedSource("来源没有足够可提取正文")
            item.update({"status": "retrieved", "resolved_url": document["final_url"],
                         "resolved_ip": document["resolved_ip"],
                         "content_type": document["content_type"],
                         "content_sha256": hashlib.sha256(document["raw"]).hexdigest(),
                         "title": (parser.title or source.get("label") or "")[:200],
                         "text_length": len(text),
                         "excerpt": text[:16000], "search_text": text})
        except Exception as exc:
            status = "blocked" if isinstance(exc, BlockedSource) else "unavailable"
            item.update({"status": status, "error": f"{type(exc).__name__}: {exc}",
                         "retry_after": (datetime.now(timezone.utc) + FAILURE_TTL).isoformat(timespec="seconds")})
        atomic_json(cached, item)
        result.append(item)
    return result


def normalize_for_match(text: str) -> str:
    """Whitespace/case-insensitive form used to locate an excerpt in a snapshot."""
    return " ".join(str(text).split()).casefold()


def locate_excerpt(excerpt: str, snapshot_text: str) -> dict | None:
    """Character range of ``excerpt`` inside the snapshot, or ``None`` when absent.

    An excerpt that cannot be found is not "roughly supported": the claim is then
    unsupported, which is exactly the defect this check exists to catch.
    """
    haystack = normalize_for_match(snapshot_text)
    needle = normalize_for_match(excerpt)
    if not needle or not haystack:
        return None
    index = haystack.find(needle)
    if index < 0:
        return None
    return {"start": index, "end": index + len(needle)}


def verify_claims(research, evidence: list[dict]) -> list[dict]:
    """Check every claim against the snapshot that was actually fetched.

    Retrieval, parsing and claim support are separate states: a source can be
    ``retrieved`` while an excerpt is missing from it, and an unfetched source can
    never support anything.  The result is per claim, with the position of the
    excerpt in the snapshot when it was found.
    """
    results = []
    by_url = {item.get("url"): item for item in evidence}
    for claim in getattr(research, "claims", []):
        indices = [claim.source_index, *[i for i in claim.evidence_refs if i != claim.source_index]]
        sources = []
        for index in indices:
            source = research.sources[index] if index < len(research.sources) else None
            snapshot = by_url.get(source.url) if source else None
            sources.append({"source_index": index, "url": source.url if source else None,
                            "snapshot": snapshot})
        primary = sources[0]["snapshot"] if sources else None
        entry = {"claim_id": claim.claim_id, "statement": claim.statement,
                 "scope": claim.scope, "importance": claim.importance,
                 "source_index": claim.source_index,
                 "evidence_refs": list(claim.evidence_refs),
                 "source_url": sources[0]["url"] if sources else None}
        if primary is None:
            entry.update({"status": "source-missing", "detail": "来源不在研究记录中"})
        elif primary.get("status") != "retrieved":
            entry.update({"status": "source-unavailable",
                          "detail": f"来源状态 {primary.get('status')}：{primary.get('error', '')}"[:200]})
        else:
            position = locate_excerpt(claim.excerpt, primary.get("search_text") or primary.get("excerpt") or "")
            corroboration = [item for item in sources[1:]
                             if item["snapshot"] and item["snapshot"].get("status") == "retrieved"
                             and locate_excerpt(claim.excerpt, item["snapshot"].get("search_text")
                                                or item["snapshot"].get("excerpt") or "")]
            if position is None:
                entry.update({"status": "excerpt-missing",
                              "detail": "抓取到的正文里找不到这段节选",
                              "content_sha256": primary.get("content_sha256"),
                              "title": primary.get("title")})
            else:
                entry.update({"status": "supported", "position": position,
                              "content_sha256": primary.get("content_sha256"),
                              "retrieved_at": primary.get("retrieved_at"),
                              "title": primary.get("title"),
                              "corroborating_sources": len(corroboration)})
        results.append(entry)
    return results


def coverage_summary(checks: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for entry in checks:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return {"claims": len(checks), "by_status": counts,
            "key_claims": sum(1 for entry in checks if entry.get("importance") == "key"),
            "supported_key_claims": sum(1 for entry in checks
                                        if entry.get("importance") == "key"
                                        and entry["status"] == "supported")}
