"""Root conftest — register custom pytest markers."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "llm: mark test as requiring a live LLM API call (excluded from CI with -m 'not llm')",
    )
