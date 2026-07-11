from __future__ import annotations

from typing import Protocol

from agents.schemas import AgentDecision
from game.engine import GameEngine


class AgentController(Protocol):
    def decide(self, engine: GameEngine, player_id: str) -> AgentDecision:
        """Return one bounded structured decision for the current phase."""

