"""Behavior: mapping remote resource URLs to local mirror paths."""

from qxconf.config import is_resource_line, url_to_relpath


def test_filter_url_mirrors_host_and_path():
    url = (
        "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/"
        "master/rule/QuantumultX/China/China.list"
    )
    assert url_to_relpath(url, "rules") == (
        "rules/raw.githubusercontent.com/blackmatrix7/ios_rule_script/"
        "master/rule/QuantumultX/China/China.list"
    )


def test_rewrite_url_uses_its_subdir():
    url = "https://example.com/path/rw.snippet"
    assert url_to_relpath(url, "rewrites") == "rewrites/example.com/path/rw.snippet"


def test_query_string_gets_hashed_suffix_to_stay_unique():
    a = url_to_relpath("https://h.com/sub?token=aaa", "rules")
    b = url_to_relpath("https://h.com/sub?token=bbb", "rules")
    assert a != b
    assert a.startswith("rules/h.com/sub.")


def test_only_http_lines_are_treated_as_resources():
    assert is_resource_line("https://x.com/a.list, tag=A, enabled=true")
    assert is_resource_line("http://x.com/a.list")
    assert not is_resource_line(";https://x.com/a.list, enabled=false")
    assert not is_resource_line("# a comment")
    assert not is_resource_line("geo_location_checker = http://ip-api.com/json/")
