"""Pytest configuration for api tests."""

import os

import pytest


@pytest.fixture(autouse=True)
def reset_env():
    """Reset environment variables between tests."""
    original = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original)
