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

    # 远程重写规则
    [rewrite_remote]
    https://example.com/path/rw.snippet, tag = RW, enabled = true

    [filter_local]
    final, Final

    # 定时任务
    [task_local]
    event-interaction https://example.com/check.js, tag = T, enabled = true

    [mitm]
    hostname = -x.com
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

    # [server_remote] entry in QX syntax: the URL is the first comma field
    assert (
        "http://b/clash/clash.yaml, tag=lan, "
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
    assert "http://b/clash/clash.yaml, tag=prod," in text


def _section_body(text: str, name: str) -> list[str]:
    """Non-blank, non-comment lines between [name] and the next [section]."""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == f"[{name}]")
    body = []
    for ln in lines[start + 1 :]:
        if ln.strip().startswith("[") and ln.strip().endswith("]"):
            break
        if ln.strip() and not ln.lstrip().startswith("#"):
            body.append(ln)
    return body


def test_disable_rewrite_remote_empties_section_and_skips_download(tmp_path):
    src, clash, out = _write_inputs(tmp_path)
    calls = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return b"data"

    result = build(
        src, "http://b", clash, out, fetcher=fetch, disable_rewrite_remote=True
    )
    text = (out / "QX_Config.conf").read_text(encoding="utf-8")

    # QX needs the header to exist; only the body is dropped, nothing fetched
    assert "[rewrite_remote]" in text
    assert _section_body(text, "rewrite_remote") == []
    assert "rw.snippet" not in text
    assert "http://b/rewrites/" not in text
    assert not any("rw.snippet" in url for url in calls)
    assert not (out / "rewrites").exists()
    assert result.rewrite_count == 0

    # neighbouring sections are unaffected
    assert result.filter_count == 1
    assert "rules/raw.githubusercontent.com/foo/bar/China.list" in text
    assert "[filter_local]" in text
    assert "[task_local]" in text


def test_disable_task_local_empties_section_keeping_header(tmp_path):
    src, clash, out = _write_inputs(tmp_path)
    build(src, "http://b", clash, out, fetcher=lambda u: b"x", disable_task_local=True)
    text = (out / "QX_Config.conf").read_text(encoding="utf-8")

    # header kept (app requires it), body emptied
    assert "[task_local]" in text
    assert _section_body(text, "task_local") == []
    assert "event-interaction" not in text

    # the next section's header survives intact
    assert "[mitm]" in text
    assert "hostname = -x.com" in text
    # an earlier section is untouched too
    assert "[filter_local]" in text


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
