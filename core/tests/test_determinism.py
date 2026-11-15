import json

import pytest
from django.core.management import call_command

from core.services.snapshots import compute_dam_state


@pytest.mark.django_db
def test_compute_dam_state_is_deterministic():
    call_command(
        "seed_hydro_data",
        reset=True,
        as_of="2026-11-13",
        country="DZA",
        years=3,
        dams="beni-haroun",
        seed=42,
        verbosity=0,
    )
    first = compute_dam_state("beni-haroun", "2026-11-13")
    second = compute_dam_state("beni-haroun", "2026-11-13")
    for payload in (first, second):
        payload.pop("snapshot_id", None)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["hri"] == pytest.approx(81.05, abs=0.02)
