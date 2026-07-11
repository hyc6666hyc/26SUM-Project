from __future__ import annotations

from game.enums import Faction, HealthStatus
from game.models import GameState, Player


def player_score(state: GameState, player: Player, shelter_survival: bool, goal_completed: bool) -> int:
    """Calculate the documented MVP score from deterministic metrics."""
    metrics = player.metrics
    if player.hidden_faction == Faction.SABOTEUR:
        score = 60 if not shelter_survival else 0
        if player.health != HealthStatus.EXPELLED:
            score += 20
        score += metrics.get("sabotage_count", 0) * 10
        score += metrics.get("misleading_votes", 0) * 8
        score += metrics.get("wrong_expulsions_caused", 0) * 10
        if player.expelled_day is not None and player.expelled_day < 4:
            score -= 30
        return score

    score = 50 if shelter_survival else 0
    score += 30 if goal_completed else 0
    score += metrics.get("repair_count", 0) * 5
    score += metrics.get("heal_count", 0) * 5
    score += metrics.get("proposals_passed", 0) * 3
    score += metrics.get("promises_kept", 0) * 2
    score -= metrics.get("promises_broken", 0) * 5
    if player.health == HealthStatus.EXPELLED:
        score -= 20
    return score
