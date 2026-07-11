from __future__ import annotations

from typing import Any

from game.engine import GameEngine


class PlayerView:
    """A player-bound capability that cannot request another player's private view."""

    __slots__ = ("__engine", "player_id")

    def __init__(self, engine: GameEngine, player_id: str) -> None:
        engine.get_public_state(player_id)  # validates player id
        self.__engine = engine
        self.player_id = player_id

    def public_state(self) -> dict[str, Any]:
        return self.__engine.get_public_state(self.player_id)

    def private_state(self) -> dict[str, Any]:
        return self.__engine.get_private_state(self.player_id)

    def current_event(self) -> dict[str, Any] | None:
        return self.__engine.get_current_event(self.player_id)

    def recent_messages(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.__engine.get_recent_messages(self.player_id, limit)

    def visible_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.__engine.get_visible_logs(self.player_id, limit)

    def relationships(self) -> dict[str, dict[str, Any]]:
        return self.__engine.get_relationships(self.player_id)

    def available_actions(self) -> list[dict[str, Any]]:
        return self.__engine.get_available_actions(self.player_id)

