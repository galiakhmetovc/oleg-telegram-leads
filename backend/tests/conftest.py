from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--runslow",
        action="store_true",
        default=False,
        help="run slow NLP integration tests",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "slow: slow NLP integration tests")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--runslow"):
        return

    skip_slow = pytest.mark.skip(reason="need --runslow to run slow NLP integration tests")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
