from __future__ import annotations

import pytest

from game.engine import GameEngine
from game.enums import GamePhase


@pytest.fixture
def engine() -> GameEngine:
    return GameEngine()


def enter_action(engine: GameEngine) -> None:
    assert engine.advance_phase() == GamePhase.DISCUSSION
    assert engine.advance_phase() == GamePhase.ACTION


def enter_voting(engine: GameEngine) -> None:
    assert engine.advance_phase() == GamePhase.ACTION
    assert engine.advance_phase() == GamePhase.VOTING

