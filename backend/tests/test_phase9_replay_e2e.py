from __future__ import annotations

import pytest

pytest.importorskip("celery")

from tradingbot.worker.replay_tasks import run_replay_regression


@pytest.mark.replay
def test_phase9_replay_regression_matches_expected_snapshot() -> None:
    result = run_replay_regression("AAPL")

    assert result["symbol"] == "AAPL"
    assert result["matches_expected"] is True
    snapshot = result["snapshot"]
    assert isinstance(snapshot, dict)
    assert snapshot["trade_count"] >= 1


@pytest.mark.replay
def test_phase9_replay_regression_is_deterministic() -> None:
    first = run_replay_regression("AAPL")
    second = run_replay_regression("AAPL")

    assert first["digest"] == second["digest"]
    assert first["snapshot"] == second["snapshot"]
