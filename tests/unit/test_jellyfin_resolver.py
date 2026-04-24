"""Tests for the resolver against a fake Jellyfin."""

from __future__ import annotations

import pytest

from jfin2etv.jellyfin.query import parse_query
from jfin2etv.jellyfin.resolver import QueryResolver, QueryResolverError
from tests.fake_jellyfin import FakeJellyfinClient


@pytest.fixture
def fake():
    fx = FakeJellyfinClient(
        items_db=[
            {"Id": "m1", "Name": "Fast Movie", "Type": "Movie",
             "Genres": ["Action"], "Tags": ["classic"], "ParentId": "lib-movies",
             "RunTimeTicks": 5400 * 10_000_000, "ProductionYear": 1995, "CommunityRating": 8.2},
            {"Id": "m2", "Name": "Horror Flick", "Type": "Movie",
             "Genres": ["Horror"], "Tags": [], "ParentId": "lib-movies",
             "RunTimeTicks": 4800 * 10_000_000, "ProductionYear": 1998, "CommunityRating": 6.5},
            {"Id": "ep1", "Name": "Simpsons S1E1", "Type": "Episode",
             "SeriesId": "simpsons", "Genres": ["Comedy"]},
            {"Id": "b1", "Name": "Bumper A", "Type": "Movie",
             "Tags": ["bumper", "classicrock_pre"], "Genres": []},
        ],
        series={"The Simpsons": "simpsons"},
        libraries={"Movies": "lib-movies"},
    )
    return fx


@pytest.mark.asyncio
async def test_and_intersection(fake):
    r = QueryResolver(fake)
    items = await r.resolve(parse_query('type:movie AND genre:Action'))
    assert [i["Id"] for i in items] == ["m1"]


@pytest.mark.asyncio
async def test_or_union(fake):
    r = QueryResolver(fake)
    items = await r.resolve(parse_query("type:movie OR type:episode"))
    ids = {i["Id"] for i in items}
    assert ids == {"m1", "m2", "b1", "ep1"}


@pytest.mark.asyncio
async def test_bounded_not_works(fake):
    r = QueryResolver(fake)
    items = await r.resolve(parse_query('library:"Movies" AND NOT genre:Horror'))
    assert [i["Id"] for i in items] == ["m1"]


@pytest.mark.asyncio
async def test_unbounded_not_raises(fake):
    r = QueryResolver(fake)
    with pytest.raises(QueryResolverError, match="unbounded NOT"):
        await r.resolve(parse_query("NOT genre:Horror"))


@pytest.mark.asyncio
async def test_series_resolution(fake):
    r = QueryResolver(fake)
    items = await r.resolve(parse_query('series:"The Simpsons"'))
    assert [i["Id"] for i in items] == ["ep1"]


@pytest.mark.asyncio
async def test_runtime_comparison(fake):
    r = QueryResolver(fake)
    # 80 minutes = 4800s; runtime:<01:30:00 means under 5400s
    items = await r.resolve(parse_query("runtime:<01:29:00"))
    assert [i["Id"] for i in items] == ["m2"]


@pytest.mark.asyncio
async def test_rating_client_side(fake):
    r = QueryResolver(fake)
    # rating is parsed via Comparison where `seconds` is reused for the number
    items = await r.resolve(parse_query("rating:>7.5"))
    assert [i["Id"] for i in items] == ["m1"]


@pytest.mark.asyncio
async def test_cache_hit_returns_same_list(fake):
    r = QueryResolver(fake)
    e = parse_query("type:movie")
    a = await r.resolve(e)
    b = await r.resolve(e)
    assert a is b  # cached result object is reused
