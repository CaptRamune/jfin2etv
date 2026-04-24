"""Jellyfin query expression parser (DESIGN.md §5.8).

Grammar::

    expr       := term ( ( "AND" | "OR" ) term )*
                | "NOT" term
    term       := "(" expr ")" | atom
    atom       := field ":" value
    field      := "type" | "genre" | "tag" | "series" | "studio" | "year"
                | "runtime" | "collection" | "library" | "rating" | "person"
    value      := literal | quoted | range | comparison
    literal    := [A-Za-z0-9_.-]+
    quoted     := "..."  (escape " as \\")
    range      := N..M
    comparison := (<|>|<=|>=) duration   (duration is HH:MM:SS or PTxx)

Produces a typed AST (`And`, `Or`, `Not`, `Atom`) with operator precedence
`NOT > AND > OR` and left-to-right associativity for AND/OR.
"""

from __future__ import annotations

from dataclasses import dataclass


class QueryParseError(ValueError):
    pass


# ---- AST ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Atom:
    field: str
    value: Value


@dataclass(frozen=True, slots=True)
class And:
    left: Expr
    right: Expr


@dataclass(frozen=True, slots=True)
class Or:
    left: Expr
    right: Expr


@dataclass(frozen=True, slots=True)
class Not:
    expr: Expr


Expr = And | Or | Not | Atom


# ---- Value tags -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Literal:
    text: str


@dataclass(frozen=True, slots=True)
class Quoted:
    text: str


@dataclass(frozen=True, slots=True)
class Range:
    lo: int
    hi: int


@dataclass(frozen=True, slots=True)
class Comparison:
    op: str  # "<", ">", "<=", ">="
    seconds: float


Value = Literal | Quoted | Range | Comparison


ALLOWED_FIELDS = frozenset(
    {
        "type",
        "genre",
        "tag",
        "series",
        "studio",
        "year",
        "runtime",
        "collection",
        "library",
        "rating",
        "person",
    }
)


# ---- Tokenizer ------------------------------------------------------------


def _parse_duration(text: str) -> float:
    t = text.strip()
    if t.startswith("PT"):
        total = 0.0
        acc = ""
        for ch in t[2:]:
            if ch.isdigit() or ch == ".":
                acc += ch
            elif ch.upper() == "H":
                total += float(acc) * 3600
                acc = ""
            elif ch.upper() == "M":
                total += float(acc) * 60
                acc = ""
            elif ch.upper() == "S":
                total += float(acc)
                acc = ""
            else:
                raise QueryParseError(f"bad duration char {ch!r} in {text!r}")
        return total
    parts = t.split(":")
    if not 1 <= len(parts) <= 3:
        raise QueryParseError(f"bad duration {text!r}")
    h = int(parts[0]) if len(parts) == 3 else 0
    m = int(parts[-2]) if len(parts) >= 2 else 0
    s = float(parts[-1])
    return h * 3600 + m * 60 + s


class _Tokenizer:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self.n = len(text)

    def peek(self) -> str:
        return self.text[self.pos] if self.pos < self.n else ""

    def eof(self) -> bool:
        return self.pos >= self.n

    def skip_ws(self) -> None:
        while self.pos < self.n and self.text[self.pos].isspace():
            self.pos += 1

    def consume_keyword(self, keyword: str) -> bool:
        self.skip_ws()
        end = self.pos + len(keyword)
        if (
            end <= self.n
            and self.text[self.pos : end].upper() == keyword.upper()
            and (end == self.n or not self.text[end].isalnum())
        ):
            self.pos = end
            return True
        return False

    def consume_char(self, ch: str) -> bool:
        self.skip_ws()
        if self.pos < self.n and self.text[self.pos] == ch:
            self.pos += 1
            return True
        return False

    def read_quoted(self) -> str:
        assert self.text[self.pos] == '"'
        self.pos += 1
        out: list[str] = []
        while self.pos < self.n:
            ch = self.text[self.pos]
            if ch == "\\" and self.pos + 1 < self.n and self.text[self.pos + 1] == '"':
                out.append('"')
                self.pos += 2
            elif ch == '"':
                self.pos += 1
                return "".join(out)
            else:
                out.append(ch)
                self.pos += 1
        raise QueryParseError("unterminated quoted string")

    def read_literal(self) -> str:
        start = self.pos
        while self.pos < self.n and (self.text[self.pos].isalnum() or self.text[self.pos] in "_.-"):
            self.pos += 1
        if self.pos == start:
            raise QueryParseError(f"expected literal at position {start}")
        return self.text[start : self.pos]


# ---- Parser ---------------------------------------------------------------


def parse_query(text: str) -> Expr:
    tok = _Tokenizer(text)
    tree = _parse_or(tok)
    tok.skip_ws()
    if not tok.eof():
        raise QueryParseError(f"unexpected trailing input at {tok.pos}: {text[tok.pos:]!r}")
    return tree


def _parse_or(tok: _Tokenizer) -> Expr:
    left = _parse_and(tok)
    while True:
        saved = tok.pos
        if tok.consume_keyword("OR"):
            right = _parse_and(tok)
            left = Or(left, right)
        else:
            tok.pos = saved
            return left


def _parse_and(tok: _Tokenizer) -> Expr:
    left = _parse_not(tok)
    while True:
        saved = tok.pos
        if tok.consume_keyword("AND"):
            right = _parse_not(tok)
            left = And(left, right)
        else:
            tok.pos = saved
            return left


def _parse_not(tok: _Tokenizer) -> Expr:
    saved = tok.pos
    if tok.consume_keyword("NOT"):
        return Not(_parse_not(tok))
    tok.pos = saved
    return _parse_term(tok)


def _parse_term(tok: _Tokenizer) -> Expr:
    tok.skip_ws()
    if tok.consume_char("("):
        inner = _parse_or(tok)
        if not tok.consume_char(")"):
            raise QueryParseError(f"expected ')' at position {tok.pos}")
        return inner
    return _parse_atom(tok)


def _parse_atom(tok: _Tokenizer) -> Atom:
    tok.skip_ws()
    field = tok.read_literal().lower()
    if field not in ALLOWED_FIELDS:
        raise QueryParseError(
            f"unknown field {field!r}; allowed: {sorted(ALLOWED_FIELDS)}"
        )
    if not tok.consume_char(":"):
        raise QueryParseError(f"expected ':' after field {field!r}")
    tok.skip_ws()
    value = _parse_value(tok, field)
    return Atom(field=field, value=value)


def _parse_value(tok: _Tokenizer, field: str) -> Value:
    tok.skip_ws()
    ch = tok.peek()
    if not ch:
        raise QueryParseError("unexpected end of expression at value")
    if ch == '"':
        return Quoted(tok.read_quoted())
    if ch in ("<", ">"):
        op = ch
        tok.pos += 1
        if tok.peek() == "=":
            op += "="
            tok.pos += 1
        tok.skip_ws()
        # Duration may contain colons (HH:MM:SS) so widen beyond read_literal.
        start = tok.pos
        while tok.pos < tok.n and (
            tok.text[tok.pos].isalnum() or tok.text[tok.pos] in ".:_-"
        ):
            tok.pos += 1
        if tok.pos == start:
            raise QueryParseError(f"expected duration at {start}")
        dur = tok.text[start : tok.pos]
        return Comparison(op, _parse_duration(dur))
    # literal — possibly a range "N..M"
    start = tok.pos
    lit = tok.read_literal()
    if ".." in lit:
        lo, _, hi = lit.partition("..")
        try:
            return Range(int(lo), int(hi))
        except ValueError as e:
            raise QueryParseError(f"bad range {lit!r} at {start}") from e
    return Literal(lit)


# ---- Helpers for callers --------------------------------------------------


def collect_fields(expr: Expr) -> set[str]:
    """Return the set of atom fields appearing anywhere in the expression."""
    if isinstance(expr, Atom):
        return {expr.field}
    if isinstance(expr, And | Or):
        return collect_fields(expr.left) | collect_fields(expr.right)
    if isinstance(expr, Not):
        return collect_fields(expr.expr)
    return set()


def has_not(expr: Expr) -> bool:
    if isinstance(expr, Not):
        return True
    if isinstance(expr, And | Or):
        return has_not(expr.left) or has_not(expr.right)
    return False


def canonical(expr: Expr) -> str:
    """Deterministic stringification used for caching / hashing."""
    if isinstance(expr, Atom):
        v = expr.value
        if isinstance(v, Literal):
            return f"{expr.field}:{v.text}"
        if isinstance(v, Quoted):
            escaped = v.text.replace('"', '\\"')
            return f'{expr.field}:"{escaped}"'
        if isinstance(v, Range):
            return f"{expr.field}:{v.lo}..{v.hi}"
        if isinstance(v, Comparison):
            return f"{expr.field}:{v.op}{v.seconds}"
    if isinstance(expr, Not):
        return f"NOT {canonical(expr.expr)}"
    if isinstance(expr, And):
        return f"({canonical(expr.left)} AND {canonical(expr.right)})"
    if isinstance(expr, Or):
        return f"({canonical(expr.left)} OR {canonical(expr.right)})"
    raise AssertionError(f"unreachable: {expr!r}")


__all__ = [
    "ALLOWED_FIELDS",
    "And",
    "Atom",
    "Comparison",
    "Expr",
    "Literal",
    "Not",
    "Or",
    "QueryParseError",
    "Quoted",
    "Range",
    "Value",
    "canonical",
    "collect_fields",
    "has_not",
    "parse_query",
]
