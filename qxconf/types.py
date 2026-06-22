"""Shared data models for the qxconf package."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClashProxy(BaseModel):
    """A single entry from a Clash configuration's ``proxies`` list.

    Only the fields needed for Quantumult X conversion are declared; any other
    keys (``client-fingerprint``, ``alterId`` ...) are tolerated and ignored.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    type: str
    server: str
    port: int
    password: str | None = None
    cipher: str | None = None
    udp: bool | None = None
    tfo: bool | None = None
    sni: str | None = None
    skip_cert_verify: bool | None = Field(default=None, alias="skip-cert-verify")
    plugin: str | None = None
    plugin_opts: dict | None = Field(default=None, alias="plugin-opts")
    alpn: list[str] | None = None


class ConversionResult(BaseModel):
    """Outcome of converting one Clash proxy to a QX ``[server_local]`` line."""

    name: str
    type: str
    supported: bool
    tag: str | None = None
    line: str | None = None
    reason: str | None = None


class RemoteResource(BaseModel):
    """An external rule/rewrite resource that gets mirrored locally."""

    section: str  # 'filter_remote' | 'rewrite_remote'
    url: str
    relpath: str
    new_url: str


class SkippedProxy(BaseModel):
    name: str
    type: str
    reason: str


class BuildResult(BaseModel):
    config_path: str
    filter_count: int
    rewrite_count: int
    node_count: int
    downloaded_count: int = 0
    cached_count: int = 0
    skipped: list[SkippedProxy] = []
    server_remote_url: str | None = None
