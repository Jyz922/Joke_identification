import os

import pytest

from doubletake.config import DEFAULT_SETTINGS


def pytest_collection_modifyitems(config, items):
    key = "GEMINI_API_KEY" if DEFAULT_SETTINGS.L5_BACKEND == "gemini" else "ANTHROPIC_API_KEY"
    if not os.getenv(key):
        skip = pytest.mark.skip(reason=f"{key} not set")
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(skip)
