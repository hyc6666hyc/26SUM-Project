from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """A JSON-friendly string enum."""


class GamePhase(StrEnum):
    EVENT = "EVENT"
    DISCUSSION = "DISCUSSION"
    ACTION = "ACTION"
    VOTING = "VOTING"
    RESOLUTION = "RESOLUTION"
    EXPULSION = "EXPULSION"
    FINISHED = "FINISHED"


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    INJURED = "INJURED"
    SERIOUSLY_INJURED = "SERIOUSLY_INJURED"
    UNCONSCIOUS = "UNCONSCIOUS"
    ISOLATED = "ISOLATED"
    EXPELLED = "EXPELLED"
    DEAD = "DEAD"


class Role(StrEnum):
    ENGINEER = "Engineer"
    DOCTOR = "Doctor"
    GUARD = "Guard"
    TRADER = "Trader"
    RESEARCHER = "Researcher"


class Faction(StrEnum):
    SURVIVOR = "SURVIVOR"
    SABOTEUR = "SABOTEUR"


class ActionType(StrEnum):
    EXPLORE = "explore"
    REPAIR = "repair"
    INVESTIGATE = "investigate"
    HEAL = "heal"
    CRAFT = "craft"
    SABOTAGE = "sabotage"
    STEAL = "steal"
    SEARCH = "search"
    TRANSFER_RESOURCE = "transfer_resource"
    MINOR_HEAL = "minor_heal"
    REINFORCE = "reinforce"
    PROTECT = "protect"
    REST = "rest"
    PERSUADE = "persuade"
    SPREAD_RUMOR = "spread_rumor"


class VoteChoice(StrEnum):
    SUPPORT = "support"
    OPPOSE = "oppose"
    ABSTAIN = "abstain"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    IMPLEMENTED = "implemented"


class TradeStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTERED = "countered"


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    ADMIN = "admin"


class ActionStatus(StrEnum):
    QUEUED = "queued"
    RESOLVED = "resolved"
    REJECTED = "rejected"
