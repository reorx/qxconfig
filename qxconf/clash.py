"""Convert Clash proxies into Quantumult X ``[server_local]`` lines.

The QX server_local syntax used here follows the official sample.conf
(https://github.com/crossutility/Quantumult-X/blob/master/sample.conf).
"""

from __future__ import annotations

import yaml

from .types import ClashProxy, ConversionResult


def load_proxies(yaml_text: str) -> list[ClashProxy]:
    data = yaml.safe_load(yaml_text) or {}
    raw = data.get("proxies") or []
    return [ClashProxy.model_validate(item) for item in raw]


def convert_proxies(proxies: list[ClashProxy]) -> list[ConversionResult]:
    """Convert every proxy, assigning unique, comma-safe tags."""
    tags = _unique_tags([p.name for p in proxies])
    return [convert_proxy(p, tag=tag) for p, tag in zip(proxies, tags)]


def convert_proxy(proxy: ClashProxy, tag: str | None = None) -> ConversionResult:
    tag = tag if tag is not None else _sanitize_tag(proxy.name)
    builder = _BUILDERS.get(proxy.type)
    if builder is None:
        return _unsupported(proxy, tag, f"unsupported proxy type: {proxy.type}")
    return builder(proxy, tag)


# --- per-type builders -------------------------------------------------------


def _build_ss(p: ClashProxy, tag: str) -> ConversionResult:
    plugin = (p.plugin or "").strip()
    if plugin in ("shadow-tls", "shadowtls"):
        return _unsupported(p, tag, "shadow-tls plugin is not supported by Quantumult X")
    if plugin and plugin != "obfs":
        return _unsupported(p, tag, f"unsupported ss plugin: {plugin}")

    parts = [
        f"shadowsocks={_host_port(p)}",
        f"method={p.cipher}",
        f"password={p.password}",
    ]
    if plugin == "obfs":
        opts = p.plugin_opts or {}
        obfs = "tls" if opts.get("mode") == "tls" else "http"
        parts.append(f"obfs={obfs}")
        if opts.get("host"):
            parts.append(f"obfs-host={opts['host']}")
        if obfs == "http" and opts.get("path"):
            parts.append(f"obfs-uri={opts['path']}")
    parts.append(f"fast-open={_yn(p.tfo)}")
    parts.append(f"udp-relay={_yn(p.udp)}")
    return _ok(p, tag, parts)


def _build_trojan(p: ClashProxy, tag: str) -> ConversionResult:
    parts = [f"trojan={_host_port(p)}", f"password={p.password}", "over-tls=true"]
    if p.sni:
        parts.append(f"tls-host={p.sni}")
    parts.append(f"tls-verification={_yn(not _truthy(p.skip_cert_verify))}")
    parts.append(f"fast-open={_yn(p.tfo)}")
    parts.append(f"udp-relay={_yn(p.udp)}")
    return _ok(p, tag, parts)


def _build_anytls(p: ClashProxy, tag: str) -> ConversionResult:
    parts = [f"anytls={_host_port(p)}", f"password={p.password}", "over-tls=true"]
    if p.sni:
        parts.append(f"tls-host={p.sni}")
    parts.append(f"tls-verification={_yn(not _truthy(p.skip_cert_verify))}")
    parts.append(f"udp-relay={_yn(p.udp)}")
    return _ok(p, tag, parts)


_BUILDERS = {
    "ss": _build_ss,
    "trojan": _build_trojan,
    "anytls": _build_anytls,
}


# --- helpers -----------------------------------------------------------------


def _host_port(p: ClashProxy) -> str:
    return f"{p.server}:{p.port}"


def _truthy(value) -> bool:
    return bool(value)


def _yn(value) -> str:
    return "true" if value else "false"


def _ok(p: ClashProxy, tag: str, parts: list[str]) -> ConversionResult:
    line = ", ".join(parts) + f", tag={tag}"
    return ConversionResult(name=p.name, type=p.type, supported=True, tag=tag, line=line)


def _unsupported(p: ClashProxy, tag: str, reason: str) -> ConversionResult:
    return ConversionResult(name=p.name, type=p.type, supported=False, tag=tag, reason=reason)


def _sanitize_tag(name: str) -> str:
    # Commas would break the comma-separated server_local syntax.
    return name.replace(",", " ").strip()


def _unique_tags(names: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    tags: list[str] = []
    for name in names:
        base = _sanitize_tag(name)
        counts[base] = counts.get(base, 0) + 1
        tags.append(base if counts[base] == 1 else f"{base} ({counts[base]})")
    return tags
