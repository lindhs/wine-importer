import pytest

from wine_importer.resolution_cache import ResolutionCache


@pytest.fixture
def seed_cache(tmp_path):
    """Build a resolution cache seeded from a legacy canonical CSV.

    Phase 6 removed --canonical; the cache is the only candidate source. Tests
    that used to pass a canonical CSV now seed a cache from it and pass --ct-cache.
    """

    def _seed(canonical_csv, name: str = "ct_cache.db") -> str:
        cache_path = tmp_path / name
        with ResolutionCache(cache_path) as cache:
            cache.import_canonical_csv(str(canonical_csv))
        return str(cache_path)

    return _seed
