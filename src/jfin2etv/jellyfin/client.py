"""Async Jellyfin HTTP client (DESIGN.md §5.8)."""

from __future__ import annotations

from typing import Any

import httpx

from ..logging import get_logger

logger = get_logger(__name__)


class JellyfinError(Exception):
    """Raised for non-2xx Jellyfin responses or connection errors."""


class JellyfinClient:
    """Lightweight async client.

    Only the endpoints jfin2etv needs are wrapped explicitly; everything else
    can go through `get()` / `post()`.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_s: float = 30.0,
        user_agent: str = "jfin2etv/0.1",
    ) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_s
        self._ua = user_agent
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "JellyfinClient":
        self._client = httpx.AsyncClient(
            base_url=self._base,
            timeout=self._timeout,
            headers={
                "X-Emby-Authorization": (
                    f'MediaBrowser Client="jfin2etv", Device="jfin2etv", '
                    f'DeviceId="jfin2etv", Version="0.1", Token="{self._api_key}"'
                ),
                "User-Agent": self._ua,
                "Accept": "application/json",
            },
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("JellyfinClient must be used as an async context manager")
        return self._client

    async def items(self, **params: Any) -> list[dict]:
        """Return matching items from `/Items`.

        Transparently paginates with `StartIndex`/`Limit` until all items
        are fetched or the server reports zero total.
        """
        fetched: list[dict] = []
        start = 0
        page_size = int(params.pop("Limit", 500))
        params.setdefault("Recursive", True)
        params.setdefault("Fields", "Path,RunTimeTicks,ProviderIds,Genres,Tags,PremiereDate,ProductionYear,ChapterInfo,Artists,SeriesName,SeriesId,ParentId,ParentIndexNumber,IndexNumber,Overview,CommunityRating,Name,Type,Tagline")

        while True:
            r = await self.client.get(
                "/Items",
                params={**params, "StartIndex": start, "Limit": page_size},
            )
            if r.status_code != 200:
                raise JellyfinError(f"GET /Items -> {r.status_code}: {r.text[:200]}")
            body = r.json()
            items = body.get("Items", []) or []
            fetched.extend(items)
            total = int(body.get("TotalRecordCount") or 0)
            if not items:
                break
            start += len(items)
            if total and start >= total:
                break
        return fetched

    async def resolve_series_id(self, name: str) -> str | None:
        r = await self.client.get(
            "/Items",
            params={
                "SearchTerm": name,
                "IncludeItemTypes": "Series",
                "Recursive": True,
                "Limit": 5,
            },
        )
        if r.status_code != 200:
            return None
        items = r.json().get("Items", [])
        exact = [i for i in items if (i.get("Name") or "").lower() == name.lower()]
        chosen = exact[0] if exact else (items[0] if items else None)
        return (chosen or {}).get("Id")

    async def resolve_collection_id(self, name: str) -> str | None:
        r = await self.client.get(
            "/Items",
            params={
                "SearchTerm": name,
                "IncludeItemTypes": "BoxSet",
                "Recursive": True,
                "Limit": 5,
            },
        )
        if r.status_code != 200:
            return None
        items = r.json().get("Items", [])
        exact = [i for i in items if (i.get("Name") or "").lower() == name.lower()]
        chosen = exact[0] if exact else (items[0] if items else None)
        return (chosen or {}).get("Id")

    async def resolve_library_id(self, name: str) -> str | None:
        r = await self.client.get("/Library/MediaFolders")
        if r.status_code != 200:
            return None
        folders = r.json().get("Items", [])
        for f in folders:
            if (f.get("Name") or "").lower() == name.lower():
                return f.get("Id")
        return None

    async def resolve_person_id(self, name: str) -> str | None:
        r = await self.client.get(
            "/Persons",
            params={"SearchTerm": name, "Limit": 5},
        )
        if r.status_code != 200:
            return None
        items = r.json().get("Items", [])
        exact = [i for i in items if (i.get("Name") or "").lower() == name.lower()]
        chosen = exact[0] if exact else (items[0] if items else None)
        return (chosen or {}).get("Id")


__all__ = ["JellyfinClient", "JellyfinError"]
