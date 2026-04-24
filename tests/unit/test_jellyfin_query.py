"""Unit tests for the query-expression parser."""

from __future__ import annotations

import pytest

from jfin2etv.jellyfin.query import (
    And,
    Atom,
    Comparison,
    Literal,
    Not,
    Or,
    QueryParseError,
    Quoted,
    Range,
    canonical,
    has_not,
    parse_query,
)


def test_simple_atom():
    e = parse_query("type:movie")
    assert isinstance(e, Atom) and e.field == "type"
    assert isinstance(e.value, Literal) and e.value.text == "movie"


def test_quoted_with_spaces():
    e = parse_query('series:"The Simpsons"')
    assert isinstance(e, Atom)
    assert isinstance(e.value, Quoted) and e.value.text == "The Simpsons"


def test_and_or_precedence():
    e = parse_query("type:movie AND genre:Rock OR tag:bumper")
    # should parse as ((type:movie AND genre:Rock) OR tag:bumper)
    assert isinstance(e, Or)
    assert isinstance(e.left, And)


def test_not_under_and_with_library():
    e = parse_query('library:"Movies" AND NOT genre:Horror')
    assert isinstance(e, And)
    assert isinstance(e.right, Not)
    assert has_not(e)


def test_runtime_lt_comparison():
    e = parse_query("runtime:<00:15:00")
    assert isinstance(e, Atom)
    assert isinstance(e.value, Comparison)
    assert e.value.op == "<" and e.value.seconds == 900


def test_year_range():
    e = parse_query("year:1990..1999")
    assert isinstance(e.value, Range)
    assert e.value.lo == 1990 and e.value.hi == 1999


def test_parens():
    e = parse_query("(type:movie OR type:episode) AND tag:classic")
    assert isinstance(e, And)
    assert isinstance(e.left, Or)


def test_unknown_field():
    with pytest.raises(QueryParseError, match="unknown field"):
        parse_query("nonesuch:foo")


def test_canonical_roundtrip():
    src = 'library:"Movies" AND NOT (genre:Horror OR genre:Thriller)'
    e = parse_query(src)
    s = canonical(e)
    assert "library" in s and "NOT" in s
