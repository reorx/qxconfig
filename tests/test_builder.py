"""Behavior: building a self-contained output directory end to end."""

import textwrap
from pathlib import Path

import pytest

from qxconf.builder import build

SOURCE = textwrap.dedent(
    """\
    [general]
    geo_location_checker = http://ip-api.com/json/, https://raw.githubusercontent.com/x/y/IP_API.js

    [policy]
    static = Apple, direct, proxy, img-url = https://raw.githubusercontent.com/z/icons/Apple.png

    [server_local]
    ;anytls = ADDR:PORT, password = pwd, over-tls = true, tag = sample

    [server_remote]
    ;https://isp.example.com/sub tag = ISP, enabled = true

    [filter_remote]
    https://raw.githubusercontent.com/foo/bar/China.list, tag = CN, force-policy = direct, enabled = true
    ;https://disabled.example.com/off.list, tag = Off, enabled = false

    [rewrite_remote]
    https://example.com/path/rw.snippet, tag = RW, enabled = true

    [filter_local]
    final, Final
    """
)

CLASH = textwrap.dedent(
    """\
    proxies:
      - {name: HK-A, type: ss, server: 1.2.3.4, port: 8388, cipher: aes-128-gcm, password: p1, udp: true}
      - name: SG-B
        type: anytls
        server: sg.example.com
        port: 9000
        password: p2
        sni: cover.org
        skip-cert-verify: true
      - name: Broken
        type: ss
        server: jp.example.com
        port: 8443
        cipher: aes-128-gcm
        password: p3
        plugin: shadow-tls
        plugin-opts: {host: bing.com, password: x, version: 3}
    """
)


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "QX_Config.conf"
    src.write_text(SOURCE, encoding="utf-8")
    clash = tmp_path / "clash.yaml"
    clash.write_text(CLASH, encoding="utf-8")
    out = tmp_path / "dest"

    fetched = {}

    def fake_fetch(url: str) -> bytes:
        body = f"CONTENT:{url}".encode()
        fetched[url] = body
        return body

    result = build(
        source=src,
        base_url="http://192.168.1.140:8888",
        clash_path=clash,
        out_dir=out,
        fetcher=fake_fetch,
    )
    return out, result, fetched


def test_output_config_is_written(project):
    out, result, _ = project
    conf = out / "QX_Config.conf"
    assert conf.exists()
    assert Path(result.config_path) == conf


def test_active_filter_url_is_rewritten_and_downloaded(project):
    out, result, fetched = project
    text = (out / "QX_Config.conf").read_text(encoding="utf-8")
    new_url = (
        "http://192.168.1.140:8888/rules/raw.githubusercontent.com/foo/bar/China.list"
    )
    # URL rewritten in place, the rest of the line preserved
    assert f"{new_url}, tag = CN, force-policy = direct, enabled = true" in text
    # actual content mirrored to disk
    mirror = out / "rules/raw.githubusercontent.com/foo/bar/China.list"
    assert mirror.read_bytes() == b"CONTENT:https://raw.githubusercontent.com/foo/bar/China.list"
    assert result.filter_count == 1


def test_rewrite_resource_goes_to_its_own_subdir(project):
    out, result, _ = project
    assert (out / "rewrites/example.com/path/rw.snippet").exists()
    assert result.rewrite_count == 1


def test_disabled_line_is_left_untouched_and_not_downloaded(project):
    out, _, fetched = project
    text = (out / "QX_Config.conf").read_text(encoding="utf-8")
    assert ";https://disabled.example.com/off.list, tag = Off, enabled = false" in text
    assert not (out / "rules/disabled.example.com/off.list").exists()
    assert "https://disabled.example.com/off.list" not in fetched


def test_non_rule_urls_are_not_localized(project):
    out, _, fetched = project
    text = (out / "QX_Config.conf").read_text(encoding="utf-8")
    # [general] and [policy] external URLs stay as-is
    assert "geo_location_checker = http://ip-api.com/json/, https://raw.githubusercontent.com/x/y/IP_API.js" in text
    assert "img-url = https://raw.githubusercontent.com/z/icons/Apple.png" in text
    assert "https://raw.githubusercontent.com/x/y/IP_API.js" not in fetched


def test_nodes_are_injected_into_server_local(project):
    out, result, _ = project
    text = (out / "QX_Config.conf").read_text(encoding="utf-8")
    assert "shadowsocks=1.2.3.4:8388, method=aes-128-gcm, password=p1" in text
    assert "anytls=sg.example.com:9000" in text
    # the original sample comment is preserved
    assert ";anytls = ADDR:PORT" in text
    assert result.node_count == 2


def test_unsupported_node_is_reported_not_emitted(project):
    out, result, _ = project
    text = (out / "QX_Config.conf").read_text(encoding="utf-8")
    assert "jp.example.com" not in text
    assert len(result.skipped) == 1
    assert result.skipped[0].name == "Broken"


def _write_inputs(tmp_path):
    src = tmp_path / "QX_Config.conf"
    src.write_text(SOURCE, encoding="utf-8")
    clash = tmp_path / "clash.yaml"
    clash.write_text(CLASH, encoding="utf-8")
    return src, clash, tmp_path / "dest"


def test_existing_files_are_not_redownloaded(tmp_path):
    src, clash, out = _write_inputs(tmp_path)
    calls = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return b"data"

    first = build(src, "http://b", clash, out, fetcher=fetch)
    assert first.downloaded_count == 2
    assert first.cached_count == 0
    after_first = len(calls)

    second = build(src, "http://b", clash, out, fetcher=fetch)
    assert len(calls) == after_first  # nothing re-fetched on the second run
    assert second.downloaded_count == 0
    assert second.cached_count == 2


def test_server_remote_mode_copies_clash_and_writes_subscription(tmp_path):
    src, clash, out = _write_inputs(tmp_path)

    result = build(
        src, "http://b", clash, out, fetcher=lambda u: b"x", server_remote="lan"
    )
    text = (out / "QX_Config.conf").read_text(encoding="utf-8")

    # the Clash config is copied verbatim under clash/
    copied = out / "clash" / "clash.yaml"
    assert copied.read_bytes() == clash.read_bytes()

    # [server_remote] entry in QX syntax: space before tag=, commas after
    assert (
        "http://b/clash/clash.yaml tag=lan, "
        "update-interval=172800, opt-parser=true, enabled=true"
    ) in text
    assert result.server_remote_url == "http://b/clash/clash.yaml"

    # no nodes converted into [server_local]
    assert "shadowsocks=1.2.3.4:8388" not in text
    assert "anytls=sg.example.com:9000" not in text
    assert result.node_count == 0
    assert result.skipped == []

    # the original [server_local] sample comment is untouched
    assert ";anytls = ADDR:PORT" in text
    # filter rules are still mirrored as usual
    assert result.filter_count == 1


def test_server_remote_accepts_custom_tag(tmp_path):
    src, clash, out = _write_inputs(tmp_path)
    build(src, "http://b", clash, out, fetcher=lambda u: b"x", server_remote="prod")
    text = (out / "QX_Config.conf").read_text(encoding="utf-8")
    assert "http://b/clash/clash.yaml tag=prod," in text


def test_force_redownloads_existing_files(tmp_path):
    src, clash, out = _write_inputs(tmp_path)
    calls = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return b"data"

    build(src, "http://b", clash, out, fetcher=fetch)
    after_first = len(calls)

    result = build(src, "http://b", clash, out, fetcher=fetch, force=True)
    assert len(calls) == 2 * after_first  # everything re-fetched
    assert result.downloaded_count == 2
    assert result.cached_count == 0
