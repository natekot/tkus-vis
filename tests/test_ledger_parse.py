import json

import pytest

from tkus_vis.ledger import ProviderUsage, parse_ledger

PATH = ".tkus/alice/feature/x.jsonl"
REAL = (
    '{"at": "2026-09-08T19:04:26.645Z", "since": "2026-09-08T18:55:12.388Z", '
    '"until": "2026-09-08T19:04:26.645Z", "parent": "5dc98a31357c5e2300982b64c17948bcd3d90e7a", '
    '"currency": "USD", "usd": 4.721591, "rates_version": "2026-08", '
    '"providers": [{"provider": "claude-code", "model": "claude-opus-5", "reqs": 48, '
    '"in": 96, "out": 24875, "cr": 7279392, "cw1h": 45954, "usd": 4.721591}]}'
)


def line(**fields):
    return json.dumps({"until": "2026-09-08T00:00:00Z", "since": "x", "currency": "USD", **fields})


def test_parses_a_real_entry():
    entries, problems = parse_ledger(PATH, REAL + "\n")
    assert problems == []
    [e] = entries
    assert (e.path, e.line, e.identity, e.branch) == (PATH, 1, "alice", "feature/x")
    assert (e.currency, e.usd, e.backlog) == ("USD", 4.721591, False)
    assert e.when == e.until == "2026-09-08T19:04:26.645Z"
    assert e.parent == "5dc98a31357c5e2300982b64c17948bcd3d90e7a"
    assert e.providers == (ProviderUsage("claude-code", "claude-opus-5", 48, 4.721591),)


def test_crlf_and_blank_lines_parse_the_same():
    entries, problems = parse_ledger(PATH, "\r\n" + REAL + "\r\n\r\n" + REAL + "\r\n")
    assert problems == []
    assert [e.line for e in entries] == [2, 4]
    assert all(e.usd == 4.721591 for e in entries)


def test_corrupt_lines_are_reported_and_the_rest_kept():
    entries, problems = parse_ledger(PATH, "\n".join([REAL, "{not json", "[1, 2]", REAL]))
    assert [e.line for e in entries] == [1, 4]
    assert [(p.line, p.message) for p in problems] == [
        (2, "skipped: not valid JSON"),
        (3, "skipped: not a JSON object"),
    ]


def test_unknown_fields_are_ignored_and_missing_counters_read_as_zero():
    text = line(
        usd=1.5,
        new_field={"a": 1},
        providers=[{"provider": "copilot", "model": "gpt-5", "usd": 1.5, "naiu": 7}],
    )
    [e], problems = parse_ledger(PATH, text)
    assert problems == []
    assert e.providers == (ProviderUsage("copilot", "gpt-5", 0, 1.5),)


def test_since_null_marks_install_backlog():
    [e], _ = parse_ledger(PATH, line(usd=2.0, since=None))
    assert e.backlog is True


def test_missing_currency_reads_as_usd_like_tkus():
    [e], _ = parse_ledger(PATH, json.dumps({"until": "2026-09-08T00:00:00Z", "usd": 1.0}))
    assert e.currency == "USD"


@pytest.mark.parametrize(
    "text, usd, message",
    [
        (json.dumps({"since": "x"}), 0.0, "usd is missing; counted as 0"),
        (line(usd=None), 0.0, "usd is missing; counted as 0"),
        (line(usd="2.5"), 2.5, "usd is a string; read as a number"),
        (line(usd="abc"), 0.0, "usd is not a number; counted as 0"),
        (line(usd=True), 0.0, "usd is not a number; counted as 0"),
        ('{"since": "x", "usd": NaN}', 0.0, "usd is not a finite number; counted as 0"),
    ],
)
def test_bad_usd_is_reported(text, usd, message):
    [e], problems = parse_ledger(PATH, text)
    assert e.usd == usd
    assert [(p.path, p.line, p.message) for p in problems] == [(PATH, 1, message)]


def test_malformed_providers_are_dropped_not_fatal():
    [e], problems = parse_ledger(PATH, line(usd=1.0, providers="nope"))
    assert e.providers == () and problems == []
