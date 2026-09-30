import pytest

from rules.loader import PACK_DIR, load_pack


@pytest.fixture
def pack():
    return load_pack(PACK_DIR / "foul_gravity_v1.yaml")
