from __future__ import annotations

from typing import Any

from game.engine import GameEngine


class HumanPlayer:
    """Thin permission-safe facade for a future CLI or Streamlit human client."""

    def __init__(self, engine: GameEngine, player_id: str) -> None:
        player = engine.state.players.get(player_id)
        if not player or not player.is_human:
            raise ValueError("指定玩家不是本局真人玩家")
        self.engine = engine
        self.player_id = player_id

    def view(self) -> dict[str, Any]:
        return {
            "public": self.engine.get_public_state(self.player_id),
            "private": self.engine.get_private_state(self.player_id),
            "messages": self.engine.get_recent_messages(self.player_id, 30),
            "logs": self.engine.get_visible_logs(self.player_id, 50),
            "available_actions": self.engine.get_available_actions(self.player_id),
        }

    def speak(self, content: str) -> None:
        self.engine.send_public_message(self.player_id, content)

    def private_message(self, receiver_id: str, content: str) -> None:
        self.engine.send_private_message(self.player_id, receiver_id, content)

    def propose(self, proposal: dict[str, Any]) -> str:
        return self.engine.propose_plan(self.player_id, proposal).id

    def vote(self, proposal_id: str, choice: str) -> None:
        self.engine.vote(self.player_id, proposal_id, choice)

    def propose_trade(
        self,
        receiver_id: str,
        offer: dict[str, int],
        request: dict[str, int] | None = None,
    ) -> str:
        return self.engine.propose_trade(
            self.player_id, receiver_id, offer, request or {}
        ).id

    def act(self, action: dict[str, Any]) -> None:
        self.engine.perform_action(self.player_id, action)

    def secret_act(self, action: dict[str, Any]) -> None:
        self.engine.perform_secret_action(self.player_id, action)

    def use_skill(self, skill: str, target: str | None = None) -> dict[str, Any]:
        return self.engine.use_skill(self.player_id, skill, target)

    def end_turn(self) -> None:
        self.engine.end_turn(self.player_id)

    def nominate(self, target_id: str) -> None:
        self.engine.nominate_for_expulsion(self.player_id, target_id)

    def defend(self, content: str) -> None:
        self.engine.submit_defense(self.player_id, content)

    def vote_expulsion(self, support: bool) -> None:
        self.engine.vote_expulsion(self.player_id, support)
