"""Resolve parsed query expressions to concrete Jellyfin item lists.

Implements field-to-Jellyfin mappings per DESIGN.md §5.8, including
bounded-NOT enforcement and per-run expression cache.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from ..logging import get_logger
from .client import JellyfinClient
from .query import (
    And,
    Atom,
    Comparison,
    Expr,
    Literal,
    Not,
    Or,
    Quoted,
    Range,
    canonical,
    collect_fields,
    has_not,
)

logger = get_logger(__name__)

TYPE_ALIASES = {
    "movie": "Movie",
    "episode": "Episode",
    "series": "Series",
    "music_video": "MusicVideo",
    "audio": "Audio",
    # Non-standard types — Jellyfin has no native type for bumpers or
    # commercials. Operators tag regular Movie/Video entries with the
    # relevant tag and use `tag:` alongside `type:movie`/`type:video`.
    "bumper": "Movie",
    "commercial": "Movie",
    "filler": "Movie",
    "trailer": "Trailer",
}


@dataclass(slots=True)
class ResolutionContext:
    """Mutable context carried through resolution: bounding libraries, cache."""

    client: JellyfinClient
    cache: dict[str, list[dict]] = field(default_factory=dict)
    expression_hashes: dict[str, str] = field(default_factory=dict)


def expression_hash(expr: Expr) -> str:
    return hashlib.sha256(canonical(expr).encode("utf-8")).hexdigest()


class QueryResolver:
    """Resolves a parsed `Expr` into a list of Jellyfin item dicts.

    Each call to `resolve()` is cached by the expression's canonical string
    within this resolver instance; the cache lives for the duration of one
    resolver (typically: one generator run).
    """

    def __init__(self, client: JellyfinClient) -> None:
        self.client = client
        self.cache: dict[str, list[dict]] = {}

    async def resolve(self, expr: Expr) -> list[dict]:
        self._enforce_bounded_not(expr)
        key = canonical(expr)
        if key in self.cache:
            return self.cache[key]
        items = await self._eval(expr, None)
        self.cache[key] = items
        return items

    # ---- boolean eval (threads a bounding set so `NOT` has a universe) ----

    async def _eval(self, expr: Expr, bounding: list[dict] | None) -> list[dict]:
        if isinstance(expr, Atom):
            items = await self._eval_atom(expr)
            return items if bounding is None else [i for i in items if i["Id"] in {b["Id"] for b in bounding}]
        if isinstance(expr, And):
            # Compute a bounding set from bounding atoms on either side to
            # narrow NOT under this AND.
            new_bound = bounding
            for child in (expr.left, expr.right):
                if isinstance(child, Atom) and child.field in ("library", "collection"):
                    atoms = await self._eval_atom(child)
                    if new_bound is None:
                        new_bound = atoms
                    else:
                        ids = {i["Id"] for i in atoms}
                        new_bound = [i for i in new_bound if i["Id"] in ids]
            left = await self._eval(expr.left, new_bound)
            right = await self._eval(expr.right, new_bound)
            right_ids = {i["Id"] for i in right}
            return [i for i in left if i["Id"] in right_ids]
        if isinstance(expr, Or):
            left = await self._eval(expr.left, bounding)
            right = await self._eval(expr.right, bounding)
            seen: set[str] = set()
            out: list[dict] = []
            for i in (*left, *right):
                if i["Id"] not in seen:
                    seen.add(i["Id"])
                    out.append(i)
            return out
        if isinstance(expr, Not):
            if bounding is None:
                raise ResolverQueryParseError(
                    "unbounded NOT reached runtime (bug: validate earlier)"
                )
            inner = await self._eval(expr.expr, bounding)
            inner_ids = {i["Id"] for i in inner}
            return [i for i in bounding if i["Id"] not in inner_ids]
        raise AssertionError(f"unreachable: {expr!r}")

    # ---- atom eval ----

    async def _eval_atom(self, atom: Atom) -> list[dict]:
        field = atom.field
        value = atom.value
        if field == "type":
            v = _lit_or_quoted(value)
            jtype = TYPE_ALIASES.get(v.lower())
            if jtype is None:
                raise QueryResolverError(f"unknown type: {v!r}")
            params: dict[str, Any] = {"IncludeItemTypes": jtype}
            # Non-standard "type" aliases also map to tag filters so
            # `type:bumper` only returns items tagged as bumpers.
            if v.lower() in ("bumper", "commercial", "filler"):
                params["Tags"] = v.lower()
            return await self.client.items(**params)
        if field == "genre":
            v = _lit_or_quoted(value)
            return await self.client.items(Genres=v)
        if field == "tag":
            v = _lit_or_quoted(value)
            return await self.client.items(Tags=v)
        if field == "studio":
            v = _lit_or_quoted(value)
            return await self.client.items(Studios=v)
        if field == "year":
            if isinstance(value, Literal):
                return await self.client.items(Years=str(int(value.text)))
            if isinstance(value, Range):
                years = ",".join(str(y) for y in range(value.lo, value.hi + 1))
                return await self.client.items(Years=years)
            raise QueryResolverError("year: expects literal or range")
        if field == "series":
            v = _lit_or_quoted(value)
            series_id = await self.client.resolve_series_id(v)
            if not series_id:
                return []
            return await self.client.items(ParentId=series_id, IncludeItemTypes="Episode")
        if field == "collection":
            v = _lit_or_quoted(value)
            cid = await self.client.resolve_collection_id(v)
            if not cid:
                return []
            return await self.client.items(ParentId=cid)
        if field == "library":
            v = _lit_or_quoted(value)
            lid = await self.client.resolve_library_id(v)
            if not lid:
                return []
            return await self.client.items(ParentId=lid)
        if field == "person":
            v = _lit_or_quoted(value)
            pid = await self.client.resolve_person_id(v)
            if not pid:
                return []
            return await self.client.items(PersonIds=pid)
        if field == "runtime":
            if not isinstance(value, Comparison):
                raise QueryResolverError("runtime: expects a comparison like <00:15:00")
            ticks = int(value.seconds * 10_000_000)
            params = {}
            if value.op in ("<", "<="):
                params["MaxRuntimeTicks"] = ticks
            elif value.op in (">", ">="):
                params["MinRuntimeTicks"] = ticks
            return await self.client.items(**params)
        if field == "rating":
            if not isinstance(value, Comparison):
                raise QueryResolverError("rating: expects a comparison like >7.5")
            all_items = await self.client.items()
            threshold = value.seconds  # we reuse Comparison.seconds as a number
            return [
                i for i in all_items
                if _rating_matches(i.get("CommunityRating"), value.op, threshold)
            ]
        raise QueryResolverError(f"unsupported field {field!r}")

    # ---- bounded NOT enforcement ----

    @staticmethod
    def _enforce_bounded_not(expr: Expr) -> None:
        if not has_not(expr):
            return
        fields = collect_fields(expr)
        if not (fields & {"library", "collection"}):
            raise QueryResolverError(
                "unbounded NOT: add a `library:` or `collection:` atom to the expression"
            )


class QueryResolverError(ValueError):
    pass


class QueryResolverInternalError(RuntimeError):
    pass


class ResolverQueryParseError(QueryResolverError):
    pass


def _lit_or_quoted(v: Any) -> str:
    if isinstance(v, Literal):
        return v.text
    if isinstance(v, Quoted):
        return v.text
    raise QueryResolverError(f"expected literal or quoted value, got {v!r}")


def _rating_matches(actual: Any, op: str, threshold: float) -> bool:
    if actual is None:
        return False
    try:
        v = float(actual)
    except (TypeError, ValueError):
        return False
    if op == ">":
        return v > threshold
    if op == ">=":
        return v >= threshold
    if op == "<":
        return v < threshold
    if op == "<=":
        return v <= threshold
    return False


__all__ = [
    "QueryResolver",
    "QueryResolverError",
    "ResolutionContext",
    "expression_hash",
]
