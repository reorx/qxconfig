"""Behavior: converting Clash proxies into Quantumult X [server_local] lines."""

import textwrap

import pytest

from qxconf.clash import convert_proxies, convert_proxy, load_proxies

CLASH_YAML = textwrap.dedent(
    """\
    proxies:
      - name: PlainSS
        type: ss
        server: 1.2.3.4
        port: 8388
        cipher: aes-128-gcm
        password: pass1
        udp: true
      - name: 'ObfsSS 🇭🇰'
        type: ss
        server: hk.example.com
        port: 443
        cipher: chacha20-ietf-poly1305
        password: pass2
        plugin: obfs
        plugin-opts:
          mode: http
          host: apple.com
        udp: true
        tfo: false
      - name: AnyNode
        type: anytls
        server: sg.example.com
        port: 9000
        password: pass3
        sni: cover.example.org
        skip-cert-verify: true
        udp: true
      - name: TrojanNode
        type: trojan
        server: us.example.com
        port: 443
        password: pass4
        sni: trojan.example.org
        skip-cert-verify: false
      - name: STLS
        type: ss
        server: jp.example.com
        port: 8443
        cipher: aes-128-gcm
        password: pass5
        plugin: shadow-tls
        plugin-opts:
          host: bing.com
          password: stlspw
          version: 3
    """
)


@pytest.fixture
def proxies():
    return load_proxies(CLASH_YAML)


def _by_name(results, name):
    return next(r for r in results if r.name == name)


def test_load_proxies_parses_known_and_hyphenated_fields(proxies):
    assert [p.name for p in proxies] == [
        "PlainSS",
        "ObfsSS 🇭🇰",
        "AnyNode",
        "TrojanNode",
        "STLS",
    ]
    any_node = next(p for p in proxies if p.name == "AnyNode")
    assert any_node.skip_cert_verify is True  # parsed from `skip-cert-verify`


def test_plain_ss_becomes_shadowsocks_line(proxies):
    r = convert_proxy(_by_name_proxy(proxies, "PlainSS"))
    assert r.supported
    assert r.line == (
        "shadowsocks=1.2.3.4:8388, method=aes-128-gcm, password=pass1, "
        "fast-open=false, udp-relay=true, tag=PlainSS"
    )


def test_ss_with_obfs_plugin_maps_to_obfs_fields(proxies):
    r = convert_proxy(_by_name_proxy(proxies, "ObfsSS 🇭🇰"))
    assert r.supported
    assert r.line == (
        "shadowsocks=hk.example.com:443, method=chacha20-ietf-poly1305, password=pass2, "
        "obfs=http, obfs-host=apple.com, fast-open=false, udp-relay=true, tag=ObfsSS 🇭🇰"
    )


def test_anytls_maps_sni_and_skip_cert_verify(proxies):
    r = convert_proxy(_by_name_proxy(proxies, "AnyNode"))
    assert r.supported
    assert r.line == (
        "anytls=sg.example.com:9000, password=pass3, over-tls=true, "
        "tls-host=cover.example.org, tls-verification=false, udp-relay=true, tag=AnyNode"
    )


def test_trojan_maps_sni_and_verification(proxies):
    r = convert_proxy(_by_name_proxy(proxies, "TrojanNode"))
    assert r.supported
    assert r.line == (
        "trojan=us.example.com:443, password=pass4, over-tls=true, "
        "tls-host=trojan.example.org, tls-verification=true, "
        "fast-open=false, udp-relay=false, tag=TrojanNode"
    )


def test_shadow_tls_is_reported_as_unsupported(proxies):
    r = convert_proxy(_by_name_proxy(proxies, "STLS"))
    assert not r.supported
    assert r.line is None
    assert "shadow-tls" in r.reason.lower()


def test_convert_proxies_keeps_only_supported_and_makes_tags_unique():
    dup_yaml = textwrap.dedent(
        """\
        proxies:
          - {name: Same, type: ss, server: a, port: 1, cipher: aes-128-gcm, password: p}
          - {name: Same, type: ss, server: b, port: 2, cipher: aes-128-gcm, password: p}
        """
    )
    results = convert_proxies(load_proxies(dup_yaml))
    tags = [r.tag for r in results]
    assert len(set(tags)) == 2  # second one disambiguated


def _by_name_proxy(proxies, name):
    return next(p for p in proxies if p.name == name)
