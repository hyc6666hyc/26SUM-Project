from __future__ import annotations

from game.enums import ActionType, Faction, GamePhase, Role
from game.exceptions import GameRuleError
from game.models import Action, GameState, Player


BASE_AP_COST: dict[ActionType, int] = {
    ActionType.EXPLORE: 2,
    ActionType.REPAIR: 2,
    ActionType.INVESTIGATE: 2,
    ActionType.HEAL: 2,
    ActionType.CRAFT: 2,
    ActionType.SABOTAGE: 2,
    ActionType.STEAL: 2,
    ActionType.SEARCH: 1,
    ActionType.TRANSFER_RESOURCE: 1,
    ActionType.MINOR_HEAL: 1,
    ActionType.REINFORCE: 1,
    ActionType.PROTECT: 1,
    ActionType.REST: 1,
    ActionType.PERSUADE: 1,
    ActionType.SPREAD_RUMOR: 1,
}

SECRET_ACTIONS = {ActionType.SABOTAGE, ActionType.STEAL, ActionType.SPREAD_RUMOR}


def action_ap_cost(player: Player, action_type: ActionType) -> int:
    """Return the deterministic AP cost including profession bonuses."""
    if action_type == ActionType.REPAIR and player.public_role == Role.ENGINEER:
        return 1
    if action_type == ActionType.HEAL and player.public_role == Role.DOCTOR:
        return 1
    if action_type == ActionType.INVESTIGATE and player.public_role == Role.GUARD:
        return 1
    return BASE_AP_COST[action_type]


def validate_action(state: GameState, player: Player, action: Action) -> int:
    """Validate phase, permissions, targets and AP before queueing an action."""
    if state.phase != GamePhase.ACTION:
        raise GameRuleError("当前不是行动阶段", "WRONG_PHASE")
    if state.finished:
        raise GameRuleError("游戏已经结束", "GAME_FINISHED")
    if not player.is_present:
        raise GameRuleError("离场玩家不能行动", "PLAYER_ABSENT")
    if not player.can_act:
        raise GameRuleError(f"当前健康状态 {player.health.value} 不能行动", "HEALTH_RESTRICTED")
    if player.ended_turn:
        raise GameRuleError("玩家已经结束本回合", "TURN_ENDED")

    is_secret_type = action.type in SECRET_ACTIONS
    if action.is_secret != is_secret_type:
        raise GameRuleError("秘密行动标记与行动类型不一致", "INVALID_SECRET_FLAG")
    if is_secret_type and player.hidden_faction != Faction.SABOTEUR:
        raise GameRuleError("非破坏者不能执行秘密破坏行动", "NOT_SABOTEUR")
    if is_secret_type and player.secret_actions_today >= 1:
        raise GameRuleError("每天最多执行 1 个秘密行动", "SECRET_ACTION_LIMIT")

    if action.type in {ActionType.REPAIR, ActionType.REINFORCE, ActionType.SABOTAGE}:
        if not action.target or action.target not in state.facilities:
            raise GameRuleError("必须指定有效设施", "INVALID_FACILITY")
    if action.type in {
        ActionType.HEAL,
        ActionType.MINOR_HEAL,
        ActionType.PERSUADE,
        ActionType.SPREAD_RUMOR,
    }:
        if not action.target or action.target not in state.players:
            raise GameRuleError("必须指定有效玩家", "INVALID_PLAYER")
    if action.type == ActionType.INVESTIGATE:
        valid_targets = set(state.players) | set(state.facilities)
        if state.current_event:
            valid_targets.add(state.current_event.id)
        if not action.target or action.target not in valid_targets:
            raise GameRuleError("调查目标必须是玩家、设施或当前事件", "INVALID_TARGET")
    if action.type == ActionType.PROTECT:
        if player.public_role != Role.GUARD:
            raise GameRuleError("只有警卫可以执行保护", "ROLE_RESTRICTED")
        if not action.target or action.target not in (set(state.players) | set(state.facilities)):
            raise GameRuleError("保护目标必须是有效玩家或设施", "INVALID_TARGET")
    if action.type == ActionType.TRANSFER_RESOURCE:
        if not action.target or action.target not in state.players or action.target == player.id:
            raise GameRuleError("资源转移必须指定其他有效玩家", "INVALID_PLAYER")
        if action.resource not in player.personal_resources:
            raise GameRuleError("未知个人资源", "INVALID_RESOURCE")
        if action.amount <= 0:
            raise GameRuleError("转移数量必须大于 0", "INVALID_AMOUNT")
        if player.personal_resources[action.resource] < action.amount:
            raise GameRuleError("个人资源不足", "INSUFFICIENT_RESOURCE")
    if action.type == ActionType.STEAL and action.resource not in {
        "food",
        "energy",
        "medicine",
        "parts",
    }:
        raise GameRuleError("偷窃必须指定有效公共资源", "INVALID_RESOURCE")

    cost = action_ap_cost(player, action.type)
    if player.ap < cost:
        raise GameRuleError(f"AP 不足：需要 {cost}，当前 {player.ap}", "INSUFFICIENT_AP")
    return cost


def available_action_types(state: GameState, player: Player) -> list[str]:
    """Return action names the player may currently attempt."""
    if state.phase != GamePhase.ACTION or not player.can_act or player.ended_turn:
        return []
    result = [kind.value for kind in BASE_AP_COST if action_ap_cost(player, kind) <= player.ap]
    if player.hidden_faction != Faction.SABOTEUR:
        result = [name for name in result if ActionType(name) not in SECRET_ACTIONS]
    if player.secret_actions_today >= 1:
        result = [name for name in result if ActionType(name) not in SECRET_ACTIONS]
    return result
