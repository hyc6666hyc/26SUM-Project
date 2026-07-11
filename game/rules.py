from __future__ import annotations

from math import ceil
from typing import Any

from game.enums import HealthStatus
from game.models import GameState, GoalCondition, Player


BASELINE_GOAL_DAYS = 6
COUNT_GOAL_METRICS = {
    "repair_count",
    "trades_completed",
    "events_analyzed",
    "craft_count",
    "prevented_sabotage",
    "sabotage_count",
}


def scaled_count_target(base_value: int, total_days: int) -> int:
    """Scale an achievable count target from the six-day baseline."""
    return max(1, ceil(int(base_value) * max(1, total_days) / BASELINE_GOAL_DAYS))


def scaled_saboteur_targets(total_days: int) -> tuple[int, int]:
    """Return secret-action count and facility threshold for this match length."""
    days = max(1, total_days)
    action_count = scaled_count_target(3, days)
    facility_limit = 75 if days == 1 else max(20, min(60, 25 + (6 - days) * 7))
    return action_count, facility_limit


def scale_goal_conditions(
    goal_id: str,
    conditions: list[GoalCondition],
    *,
    total_days: int,
    player_count: int,
    enable_saboteur: bool,
) -> list[GoalCondition]:
    """Make each new match's private goals achievable for its configured size."""
    if goal_id == "guard_protection" and not enable_saboteur:
        stability_target = max(20, min(65, 40 + (6 - total_days) * 5))
        return [GoalCondition("world.stability", ">=", stability_target)]

    scaled: list[GoalCondition] = []
    for condition in conditions:
        if goal_id == "guard_protection" and total_days < 3 and condition.metric == "voted_true_saboteur":
            continue
        value = int(condition.value)
        if condition.metric in COUNT_GOAL_METRICS:
            value = scaled_count_target(value, total_days)
        elif goal_id == "engineer_repair" and condition.metric == "world.energy":
            value = max(5, min(25, value + (6 - total_days) * 2))
        elif goal_id == "doctor_survival" and condition.metric == "world.present_players":
            value = max(2, min(player_count, ceil(value * player_count / 6)))
        elif goal_id == "doctor_survival" and condition.metric == "world.medicine":
            value = max(1, min(8, value + (6 - total_days)))
        elif goal_id == "saboteur_damage" and condition.metric == "lowest_sabotaged_facility_durability":
            _, value = scaled_saboteur_targets(total_days)
        scaled.append(GoalCondition(condition.metric, condition.operator, value))
    return scaled


def describe_scaled_goal(
    goal_id: str,
    conditions: list[GoalCondition],
    fallback: str,
) -> str:
    values = {condition.metric: int(condition.value) for condition in conditions}
    descriptions = {
        "engineer_repair": lambda: (
            f"至少修复 {values['repair_count']} 次设施，且游戏结束时 energy >= {values['world.energy']}。"
        ),
        "doctor_survival": lambda: (
            f"至少 {values['world.present_players']} 名玩家仍在场，且游戏结束时 medicine >= {values['world.medicine']}。"
        ),
        "trader_deals": lambda: (
            f"至少完成 {values['trades_completed']} 次交易，且个人资源价值最高。"
        ),
        "researcher_analysis": lambda: (
            f"成功分析 {values['events_analyzed']} 个事件，并制作至少 {values['craft_count']} 个特殊道具。"
        ),
        "saboteur_damage": lambda: (
            f"秘密干扰至少 {values['sabotage_count']} 次，并使任一核心设施耐久度降至 "
            f"{values['lowest_sabotaged_facility_durability']}% 或以下。"
        ),
    }
    if goal_id == "guard_protection":
        if "world.stability" in values:
            return f"本局无破坏者；游戏结束时 stability >= {values['world.stability']}。"
        prevented = values["prevented_sabotage"]
        if "voted_true_saboteur" not in values:
            return f"成功阻止 {prevented} 次破坏（短局不要求参与驱逐）。"
        return f"成功阻止 {prevented} 次破坏，并参与驱逐真正的破坏者。"
    builder = descriptions.get(goal_id)
    return builder() if builder else fallback


def active_players(state: GameState) -> list[Player]:
    return [player for player in state.players.values() if player.is_present]


def voting_players(state: GameState) -> list[Player]:
    return [player for player in state.players.values() if player.can_vote]


def collapse_reason(state: GameState) -> str | None:
    """Return the first immediate-collapse reason, or None."""
    if state.resources.stability <= 0:
        return "稳定度降至 0"
    if state.food_zero_days >= 2:
        return "食物连续 2 天为 0"
    if state.energy_zero_days >= 2:
        return "能源连续 2 天为 0"
    if len(active_players(state)) < 2:
        return "在场玩家少于 2 人"
    if state.facilities and all(facility.durability <= 0 for facility in state.facilities.values()):
        return "所有核心设施失效"
    return None


def shelter_survived(state: GameState) -> bool:
    working_facilities = sum(facility.durability > 0 for facility in state.facilities.values())
    return (
        state.resources.stability > 0
        and not (state.resources.food == 0 and state.resources.energy == 0)
        and len(active_players(state)) >= 3
        and working_facilities >= 2
    )


def improve_health(status: HealthStatus, levels: int = 1) -> HealthStatus:
    order = [
        HealthStatus.UNCONSCIOUS,
        HealthStatus.SERIOUSLY_INJURED,
        HealthStatus.INJURED,
        HealthStatus.HEALTHY,
    ]
    if status not in order:
        return status
    return order[min(len(order) - 1, order.index(status) + max(0, levels))]


def worsen_health(status: HealthStatus, levels: int = 1) -> HealthStatus:
    order = [
        HealthStatus.HEALTHY,
        HealthStatus.INJURED,
        HealthStatus.SERIOUSLY_INJURED,
        HealthStatus.UNCONSCIOUS,
        HealthStatus.DEAD,
    ]
    if status not in order:
        return status
    return order[min(len(order) - 1, order.index(status) + max(0, levels))]


def personal_resource_value(player: Player) -> int:
    weights = {"food": 1, "energy": 1, "medicine": 3, "parts": 2}
    return sum(weights.get(name, 1) * amount for name, amount in player.personal_resources.items())


def metric_value(state: GameState, player: Player, metric: str) -> int:
    if metric.startswith("world."):
        name = metric.removeprefix("world.")
        if name == "present_players":
            return len(active_players(state))
        if name == "personal_resource_rank":
            ordered = sorted(
                state.players.values(), key=lambda item: (-personal_resource_value(item), item.id)
            )
            return ordered.index(player) + 1
        if name == "lowest_facility_durability":
            return min(
                (facility.durability for facility in state.facilities.values()),
                default=100,
            )
        return state.resources.get(name)
    if metric == "lowest_sabotaged_facility_durability":
        return player.metrics.get(metric, 100)
    return player.metrics.get(metric, 0)


def condition_met(actual: int, condition: GoalCondition) -> bool:
    expected = int(condition.value)
    operations = {
        ">=": actual >= expected,
        "<=": actual <= expected,
        "==": actual == expected,
        ">": actual > expected,
        "<": actual < expected,
    }
    if condition.operator not in operations:
        raise ValueError(f"未知目标操作符: {condition.operator}")
    return operations[condition.operator]


def evaluate_private_goal(state: GameState, player: Player) -> bool:
    if not player.private_goal:
        return False
    completed = all(
        condition_met(metric_value(state, player, condition.metric), condition)
        for condition in player.private_goal.conditions
    )
    player.private_goal.completed = completed
    return completed


def apply_structured_effect(state: GameState, effect: dict[str, Any], rng: Any) -> list[str]:
    """Apply event/proposal effects without delegating any numeric rule to an LLM."""
    changes: list[str] = []
    for name, delta in effect.get("resources", {}).items():
        actual = state.resources.change(name, int(delta))
        changes.append(f"{name} {actual:+d}")
    for facility_id, delta in effect.get("facilities", {}).items():
        if facility_id in state.facilities:
            actual = state.facilities[facility_id].change(int(delta))
            changes.append(f"{facility_id} {actual:+d}")
    injury_count = int(effect.get("random_injury", 0))
    candidates = [player for player in active_players(state) if player.health != HealthStatus.UNCONSCIOUS]
    rng.shuffle(candidates)
    for player in candidates[:injury_count]:
        player.health = worsen_health(player.health)
        changes.append(f"{player.name} 受伤")
    damage = int(effect.get("random_facility_damage", 0))
    if damage and state.facilities:
        facility = rng.choice(list(state.facilities.values()))
        actual = facility.change(-damage)
        changes.append(f"{facility.id} {actual:+d}")
    return changes
