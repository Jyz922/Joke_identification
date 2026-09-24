import os

import pytest

from doubletake.config import DEFAULT_SETTINGS


@pytest.fixture(autouse=True)
def _live_gate(request):
    """Skip any live test unless DOUBLETAKE_ALLOW_LIVE=1 is explicitly set.

    An API key being present is NOT sufficient — it must be paired with the
    opt-in flag so live runs are always a conscious decision, not an accident.
    """
    if not request.node.get_closest_marker("live"):
        return
    if os.getenv("DOUBLETAKE_ALLOW_LIVE") != "1":
        pytest.skip(
            "Live tests consume paid API quota and require explicit opt-in. "
            "Set DOUBLETAKE_ALLOW_LIVE=1 to run them. "
            "Routine verification: py -3.11 -m pytest -q -m 'not live'",
        )
    from doubletake.providers import resolve_api_key_name
    key = resolve_api_key_name(DEFAULT_SETTINGS.L5_BACKEND)
    if not os.getenv(key):
        pytest.skip(f"{key} not set")
