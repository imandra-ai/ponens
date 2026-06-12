"""Unit tests need no hub server.

The parent conftest defines an autouse `set_hub_env` fixture that boots the
TraceHub app. Override it here with a no-op so the local/offline unit tests in
this subtree run without any backend.
"""

import pytest


@pytest.fixture(autouse=True)
def set_hub_env():
    yield
