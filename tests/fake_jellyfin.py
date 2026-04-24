"""Fake Jellyfin client used by unit tests.

Mimics the subset of `JellyfinClient` the resolver calls. Items are supplied
as a fixture list at construction; filter-by-query simulations match the
mapping table in DESIGN.md §5.8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FakeJellyfinClient:
    items_db: list[dict] = field(default_factory=list)
    series: dict[str, str] = field(default_factory=dict)  # name -> id
    collections: dict[str, str] = field(default_factory=dict)
    libraries: dict[str, str] = field(default_factory=dict)
    persons: dict[str, str] = field(default_factory=dict)

    async def __aenter__(self) -> FakeJellyfinClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def items(self, **params: Any) -> list[dict]:
        out = list(self.items_db)
        if itype := params.get("IncludeItemTypes"):
            wanted = set(itype.split(","))
            out = [i for i in out if i.get("Type") in wanted]
        if genres := params.get("Genres"):
            want = genres.lower()
            out = [i for i in out if any(g.lower() == want for g in i.get("Genres") or [])]
        if tags := params.get("Tags"):
            want = tags.lower()
            out = [i for i in out if any(t.lower() == want for t in i.get("Tags") or [])]
        if studios := params.get("Studios"):
            want = studios.lower()
            out = [i for i in out if any(s.lower() == want for s in i.get("Studios") or [])]
        if years := params.get("Years"):
            want_years = {int(y) for y in str(years).split(",")}
            out = [i for i in out if i.get("ProductionYear") in want_years]
        if parent := params.get("ParentId"):
            out = [i for i in out if i.get("ParentId") == parent or i.get("SeriesId") == parent]
        if (mx := params.get("MaxRuntimeTicks")) is not None:
            out = [i for i in out if i.get("RunTimeTicks") is not None and i["RunTimeTicks"] <= int(mx)]
        if (mn := params.get("MinRuntimeTicks")) is not None:
            out = [i for i in out if i.get("RunTimeTicks") is not None and i["RunTimeTicks"] >= int(mn)]
        if person_ids := params.get("PersonIds"):
            pids = set(person_ids.split(","))
            out = [
                i for i in out
                if any((p.get("Id") in pids) for p in (i.get("People") or []))
            ]
        return out

    async def resolve_series_id(self, name: str) -> str | None:
        return self.series.get(name)

    async def resolve_collection_id(self, name: str) -> str | None:
        return self.collections.get(name)

    async def resolve_library_id(self, name: str) -> str | None:
        return self.libraries.get(name)

    async def resolve_person_id(self, name: str) -> str | None:
        return self.persons.get(name)
