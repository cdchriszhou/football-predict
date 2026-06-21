"""Shared HTTP client helpers for crawlers."""
import os
from urllib.parse import urlparse

from config import SPORTTERY_DIRECT, SPORTTERY_PROXY


def get_crawler_proxy() -> str | None:
    """Return proxy URL only when non-empty; empty .env values must not break httpx."""
    proxy = (os.getenv("CRAWLER_PROXY") or "").strip()
    return proxy or None


def socks_proxy_supported() -> bool:
    """True when httpx can use socks5:// proxies (requires socksio)."""
    try:
        import socksio  # noqa: F401
        return True
    except ImportError:
        return False


def _socks5_variant(http_proxy: str) -> str | None:
    """Clash: HTTP 7890 / SOCKS5 7891 — offer both when using local mixed port."""
    if not socks_proxy_supported():
        return None
    if not http_proxy.startswith("http://"):
        return None
    host_port = http_proxy[len("http://") :]
    if ":" not in host_port:
        return None
    host, port_s = host_port.rsplit(":", 1)
    try:
        port = int(port_s)
    except ValueError:
        return None
    return f"socks5://{host}:{port + 1}"


def sporttery_proxy_attempts() -> list[tuple[str, str | None]]:
    """
    Ordered proxy attempts for sporttery.cn.

    **Domestic (China) deploy:** direct first — do not set SPORTTERY_PROXY.
    CRAWLER_PROXY is for The Odds API only; sporttery should not be forced through
    Clash unless SPORTTERY_PROXY is explicitly set.

    **Overseas deploy:** set SPORTTERY_PROXY to a China HTTP relay; see
    deploy/clash-sporttery-rules.yaml
    """
    attempts: list[tuple[str, str | None]] = []
    seen: set[str] = set()

    def _add(label: str, proxy: str | None) -> None:
        key = proxy or ""
        if key in seen:
            return
        seen.add(key)
        attempts.append((label, proxy))

    if SPORTTERY_DIRECT:
        _add("direct", None)
        return attempts

    crawler = get_crawler_proxy()

    if SPORTTERY_PROXY:
        _add("SPORTTERY_PROXY", SPORTTERY_PROXY)
        socks = _socks5_variant(SPORTTERY_PROXY)
        if socks:
            _add("SPORTTERY_SOCKS5", socks)
        return attempts

    # Default: China-hosted — try direct before any Clash/crawler proxy
    _add("direct", None)
    if crawler:
        _add("CRAWLER_PROXY", crawler)
        socks = _socks5_variant(crawler)
        if socks:
            _add("CRAWLER_SOCKS5", socks)
    return attempts


def proxy_for_sporttery(url: str) -> str | None:
    """Primary proxy for sporttery.cn — first entry in sporttery_proxy_attempts()."""
    attempts = sporttery_proxy_attempts()
    return attempts[0][1] if attempts else None


def proxy_for_url(url: str) -> str | None:
    """
    Pick proxy per target host.

    sporttery.cn uses proxy_for_sporttery(); other hosts use CRAWLER_PROXY.
    """
    host = (urlparse(url).hostname or "").lower()
    if host.endswith(".cn") or host == "sporttery.cn" or "sporttery.cn" in host:
        return proxy_for_sporttery(url)
    return get_crawler_proxy()
