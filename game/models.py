from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from game.enums import (
    ActionStatus,
    ActionType,
    Faction,
    GamePhase,
    HealthStatus,
    ProposalStatus,
    Role,
    TradeStatus,
    Visibility,
    VoteChoice,
)


@dataclass(slots=True)
class GameConfig:
    player_count: int = 6
    human_count: int = 0
    total_days: int = 6
    enable_saboteur: bool = True
    random_seed: int = 42
    normal_agent_model: str = "qwen3.6-flash"
    strategy_agent_model: str = "qwen3.7-plus"
    review_model: str = "qwen3.7-plus"
    auto_advance_delay: float = 0.2
    max_steps: int = 200

    def __post_init__(self) -> None:
        if not 3 <= self.player_count <= 12:
            raise ValueError("player_count 必须在 3 到 12 之间")
        if self.human_count not in (0, 1):
            raise ValueError("MVP 仅支持 0 或 1 名真人")
        if self.human_count > self.player_count:
            raise ValueError("human_count 不能超过 player_count")
        if self.total_days < 1:
            raise ValueError("total_days 必须大于 0")
        if self.max_steps < self.total_days * 5:
            raise ValueError("max_steps 太小，无法完成配置的游戏天数")


@dataclass(slots=True)
class Resources:
    food: int = 40
    energy: int = 35
    medicine: int = 12
    parts: int = 10
    stability: int = 70

    def get(self, name: str) -> int:
        if name not in {"food", "energy", "medicine", "parts", "stability"}:
            raise ValueError(f"未知公共资源: {name}")
        return int(getattr(self, name))

    def change(self, name: str, delta: int) -> int:
        old = self.get(name)
        upper = 100 if name == "stability" else 999
        value = max(0, min(upper, old + int(delta)))
        setattr(self, name, value)
        return value - old

    def can_afford(self, cost: dict[str, int]) -> bool:
        return all(amount >= 0 and self.get(name) >= amount for name, amount in cost.items())

    def spend(self, cost: dict[str, int]) -> None:
        if not self.can_afford(cost):
            raise ValueError("公共资源不足")
        for name, amount in cost.items():
            self.change(name, -amount)


@dataclass(slots=True)
class Facility:
    id: str
    name: str
    durability: int = 100

    @property
    def condition(self) -> str:
        if self.durability >= 80:
            return "正常"
        if self.durability >= 50:
            return "轻度损坏"
        if self.durability >= 20:
            return "严重损坏"
        return "失效"

    def change(self, delta: int) -> int:
        old = self.durability
        self.durability = max(0, min(100, old + int(delta)))
        return self.durability - old


@dataclass(slots=True)
class GoalCondition:
    metric: str
    operator: str
    value: int | str


@dataclass(slots=True)
class PrivateGoal:
    id: str
    description: str
    conditions: list[GoalCondition]
    completed: bool = False


@dataclass(slots=True)
class Relationship:
    trust: int = 50
    suspicion: int = 10
    cooperation: int = 50
    honesty: int = 50
    usefulness: int = 50
    known_promises: list[str] = field(default_factory=list)
    broken_promises: list[str] = field(default_factory=list)

    def apply(self, **deltas: int) -> None:
        for name, delta in deltas.items():
            if hasattr(self, name) and isinstance(getattr(self, name), int):
                setattr(self, name, max(0, min(100, getattr(self, name) + int(delta))))


@dataclass(slots=True)
class Player:
    id: str
    name: str
    public_role: Role
    hidden_faction: Faction = Faction.SURVIVOR
    is_human: bool = False
    health: HealthStatus = HealthStatus.HEALTHY
    ap: int = 0
    private_goal: PrivateGoal | None = None
    personal_resources: dict[str, int] = field(
        default_factory=lambda: {"food": 1, "medicine": 0, "parts": 1}
    )
    inventory: dict[str, int] = field(default_factory=dict)
    personality: dict[str, int] = field(default_factory=dict)
    current_plan: str = ""
    relationships: dict[str, Relationship] = field(default_factory=dict)
    turn_memory: list[str] = field(default_factory=list)
    key_memory: list[str] = field(default_factory=list)
    clues: list[str] = field(default_factory=list)
    promises: list[str] = field(default_factory=list)
    metrics: dict[str, int] = field(default_factory=dict)
    cooldowns: dict[str, int] = field(default_factory=dict)
    public_messages_today: int = 0
    private_chats_today: int = 0
    proposals_today: int = 0
    trades_today: int = 0
    secret_actions_today: int = 0
    ended_turn: bool = False
    expelled_day: int | None = None

    @property
    def is_present(self) -> bool:
        return self.health not in {HealthStatus.EXPELLED, HealthStatus.DEAD}

    @property
    def can_vote(self) -> bool:
        return self.health not in {
            HealthStatus.UNCONSCIOUS,
            HealthStatus.EXPELLED,
            HealthStatus.DEAD,
        }

    @property
    def can_speak(self) -> bool:
        return self.health not in {
            HealthStatus.UNCONSCIOUS,
            HealthStatus.EXPELLED,
            HealthStatus.DEAD,
        }

    @property
    def can_act(self) -> bool:
        return self.health in {HealthStatus.HEALTHY, HealthStatus.INJURED}

    def daily_ap(self) -> int:
        if self.health == HealthStatus.HEALTHY:
            return 2
        if self.health == HealthStatus.INJURED:
            return 1
        return 0

    def reset_for_day(self) -> None:
        self.ap = 0
        self.public_messages_today = 0
        self.private_chats_today = 0
        self.proposals_today = 0
        self.trades_today = 0
        self.secret_actions_today = 0
        self.ended_turn = False
        self.turn_memory.clear()
        for skill, days in list(self.cooldowns.items()):
            self.cooldowns[skill] = max(0, days - 1)


@dataclass(slots=True)
class Event:
    id: str
    title: str
    description: str
    visible_effect: str
    available_solutions: list[str]
    resource_cost: dict[str, int]
    success_effect: dict[str, Any]
    failure_effect: dict[str, Any]
    hidden_risk: str
    related_facility: str | None
    role_bonus: Role | None
    difficulty: int = 1


@dataclass(slots=True)
class Action:
    id: str
    player_id: str
    type: ActionType
    target: str | None = None
    resource: str | None = None
    amount: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    is_secret: bool = False
    ap_cost: int = 0
    status: ActionStatus = ActionStatus.QUEUED
    result: str = ""


@dataclass(slots=True)
class Proposal:
    id: str
    proposer_id: str
    title: str
    description: str
    resource_cost: dict[str, int]
    participants: list[str]
    expected_effect: dict[str, Any]
    target_event: str | None
    votes: dict[str, VoteChoice] = field(default_factory=dict)
    status: ProposalStatus = ProposalStatus.PENDING
    created_day: int = 1


@dataclass(slots=True)
class Trade:
    id: str
    sender_id: str
    receiver_id: str
    offer: dict[str, int]
    request: dict[str, int]
    is_public: bool = False
    promise: str | None = None
    status: TradeStatus = TradeStatus.PENDING
    parent_trade_id: str | None = None


@dataclass(slots=True)
class Message:
    id: str
    day: int
    phase: GamePhase
    sender_id: str
    content: str
    receiver_id: str | None = None

    @property
    def is_private(self) -> bool:
        return self.receiver_id is not None


@dataclass(slots=True)
class LogEntry:
    id: str
    day: int
    phase: GamePhase
    category: str
    message: str
    visibility: Visibility = Visibility.PUBLIC
    player_ids: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExpulsionCase:
    day: int
    nominations: dict[str, set[str]] = field(default_factory=dict)
    target_id: str | None = None
    defense: str | None = None
    votes: dict[str, bool] = field(default_factory=dict)
    resolved: bool = False
    expelled: bool = False


@dataclass(slots=True)
class GameResult:
    shelter_survived: bool
    collapse_reason: str | None
    faction_winner: str
    player_results: dict[str, dict[str, Any]]
    scores: dict[str, int]
    revealed_identities: dict[str, str]
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GameState:
    config: GameConfig
    day: int = 1
    phase: GamePhase = GamePhase.EVENT
    resources: Resources = field(default_factory=Resources)
    facilities: dict[str, Facility] = field(default_factory=dict)
    players: dict[str, Player] = field(default_factory=dict)
    current_event: Event | None = None
    proposals: dict[str, Proposal] = field(default_factory=dict)
    trades: dict[str, Trade] = field(default_factory=dict)
    pending_actions: list[Action] = field(default_factory=list)
    action_history: list[Action] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    logs: list[LogEntry] = field(default_factory=list)
    expulsion: ExpulsionCase | None = None
    food_zero_days: int = 0
    energy_zero_days: int = 0
    step_count: int = 0
    finished: bool = False
    result: GameResult | None = None
    handled_event: bool = False

    def raw_dict(self) -> dict[str, Any]:
        """Return a recursive dataclass representation for serialization helpers."""
        return asdict(self)
