import os

import pytest


def pytest_collection_modifyitems(config, items):
    if not os.getenv("ANTHROPIC_API_KEY"):
        skip = pytest.mark.skip(reason="ANTHROPIC_API_KEY not set")
        for item in items:
            if item.get_closest_marker("live"):
                item.add_marker(skip)
