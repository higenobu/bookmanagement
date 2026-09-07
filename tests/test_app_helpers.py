"""Tests for app.py's pure search helpers (no database needed)."""

import pytest

import app
from dash import html


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", ""),
        (None, ""),
        ("  hello  ", "hello"),
        ("hello   world", "hello world"),
        ("　　full width　space　", "full width space"),
        ("tab\tand\nnewline", "tab and newline"),
    ],
)
def test_normalize_search_text(raw, expected):
    assert app.normalize_search_text(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", []),
        (None, []),
        ("one", ["one"]),
        ("one two three", ["one", "two", "three"]),
        ("a  b", ["a", "b"]),
    ],
)
def test_split_tokens(raw, expected):
    assert app.split_tokens(raw) == expected


def test_normalize_then_split_handles_full_width_input():
    normalized = app.normalize_search_text("　夏目　漱石　")
    assert app.split_tokens(normalized) == ["夏目", "漱石"]


def _flatten(nodes):
    """Render highlight nodes back to plain text for easy assertions."""
    out = []
    for n in nodes:
        out.append(n.children if isinstance(n, html.Mark) else n)
    return "".join(out)


def _marks(nodes):
    return [n.children for n in nodes if isinstance(n, html.Mark)]


def test_highlight_no_tokens_returns_text_unchanged():
    assert app.highlight_text_nodes("Moby Dick", []) == ["Moby Dick"]


def test_highlight_empty_text_returns_text_unchanged():
    assert app.highlight_text_nodes("", ["a"]) == [""]


def test_highlight_wraps_match_and_preserves_surrounding_text():
    nodes = app.highlight_text_nodes("Moby Dick", ["Dick"])
    assert _flatten(nodes) == "Moby Dick"
    assert _marks(nodes) == ["Dick"]


def test_highlight_is_case_insensitive_but_keeps_original_casing():
    nodes = app.highlight_text_nodes("Moby Dick", ["moby"])
    assert _marks(nodes) == ["Moby"]


def test_highlight_marks_every_occurrence_of_multiple_tokens():
    nodes = app.highlight_text_nodes("the cat and the hat", ["the", "cat"])
    assert _flatten(nodes) == "the cat and the hat"
    assert _marks(nodes) == ["the", "cat", "the"]


def test_highlight_prefers_longest_token_on_overlap():
    # "foobar" must win over "foo", otherwise the longer match is split apart.
    nodes = app.highlight_text_nodes("a foobar b", ["foo", "foobar"])
    assert _marks(nodes) == ["foobar"]
    assert _flatten(nodes) == "a foobar b"


def test_highlight_escapes_regex_metacharacters_in_tokens():
    nodes = app.highlight_text_nodes("cost is 3.50 (net)", ["(net)"])
    assert _marks(nodes) == ["(net)"]
    assert _flatten(nodes) == "cost is 3.50 (net)"
