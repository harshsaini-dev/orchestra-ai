"""Old single-company regression tests explicitly opt into the isolated legacy UI."""

import pytest


@pytest.fixture(autouse=True)
def legacy_regression_opt_in(request, monkeypatch):
    if request.path.name in {
        "test_workflows.py",
        "test_jobs.py",
        "test_message_bus.py",
        "test_rag.py",
    }:
        monkeypatch.setenv("ORCHESTRA_LEGACY", "1")
