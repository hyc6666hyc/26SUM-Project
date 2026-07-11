from __future__ import annotations

from typing import Any

from game.enums import Visibility
from game.models import GameState


def build_postgame_review(state: GameState, scores: dict[str, int]) -> dict[str, Any]:
    """Build a deterministic, displayable review without hidden reasoning traces."""
    public_messages = [
        entry.message
        for entry in state.logs
        if entry.category == "public_message" and entry.visibility == Visibility.PUBLIC
    ]
    votes = [
        entry.message
        for entry in state.logs
        if entry.category in {"proposal_vote_result", "expulsion"}
        and entry.visibility == Visibility.PUBLIC
    ]
    trades = [
        entry.message
        for entry in state.logs
        if entry.category == "trade" and entry.visibility == Visibility.PUBLIC
    ]
    secret_actions = [
        {
            "actor_id": action.player_id,
            "type": action.type.value,
            "target": action.target,
            "result": action.result,
        }
        for action in state.action_history
        if action.is_secret
    ]
    promises = {
        player.id: {
            "made": list(player.promises),
            "known_broken": [
                promise
                for relationship in player.relationships.values()
                for promise in relationship.broken_promises
            ],
        }
        for player in state.players.values()
    }
    return {
        "key_public_messages": public_messages[:8],
        "key_vote_and_expulsion_results": votes,
        "public_trades": trades,
        "revealed_secret_actions": secret_actions,
        "promises": promises,
        "score_ranking": [
            player_id
            for player_id, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        ],
    }
