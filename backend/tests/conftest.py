"""Shared pytest fixtures.

Redirects the parquet data store to a temporary directory for the whole test
session so tests never touch the real ``data_store/``.
"""

import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def _isolated_data_store(tmp_path_factory):
    store = tmp_path_factory.mktemp("data_store")
    original = settings.DATA_STORE_DIR
    settings.DATA_STORE_DIR = store
    yield
    settings.DATA_STORE_DIR = original
