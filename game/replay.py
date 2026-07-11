from __future__ import annotations

from typing import Any

from game.engine import GameEngine
from game.enums import Visibility


def public_timeline(engine: GameEngine, day: int | None = None) -> list[dict[str, Any]]:
    """Build a replayable public timeline, optionally restricted to one day."""
    entries = [
        entry
        for entry in engine.state.logs
        if entry.visibility == Visibility.PUBLIC and (day is None or entry.day == day)
    ]
    return [
        {
            "id": entry.id,
            "day": entry.day,
            "phase": entry.phase.value,
            "category": entry.category,
            "message": entry.message,
            "data": dict(entry.data),
        }
        for entry in entries
    ]


def key_events(engine: GameEngine) -> list[dict[str, Any]]:
    important = {
        "event",
        "proposal_vote_result",
        "proposal_execution",
        "secret_incident",
        "expulsion",
        "game_result",
    }
    return [item for item in public_timeline(engine) if item["category"] in important]

