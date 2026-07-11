from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionChoice(StrictModel):
    type: str
    target: str | None = None
    resource: str | None = None
    amount: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    secret: bool = False


class PrivateMessageChoice(StrictModel):
    receiver_id: str
    content: str


class ProposalChoice(StrictModel):
    title: str
    description: str
    resource_cost: dict[str, int]
    participants: list[str]
    target_event: str


class TradeChoice(StrictModel):
    receiver_id: str
    offer: dict[str, int]
    request: dict[str, int] = Field(default_factory=dict)
    is_public: bool = False
    promise: str | None = None


class RelationshipDelta(StrictModel):
    trust_delta: int = 0
    suspicion_delta: int = 0
    cooperation_delta: int = 0


class AgentDecision(StrictModel):
    """Only displayable strategy output; hidden chain-of-thought is never requested."""

    public_message: str | None = None
    private_messages: list[PrivateMessageChoice] = Field(default_factory=list)
    proposal: ProposalChoice | None = None
    trade: TradeChoice | None = None
    votes: dict[str, Literal["support", "oppose", "abstain"]] = Field(default_factory=dict)
    actions: list[ActionChoice] = Field(default_factory=list)
    expulsion_nomination: str | None = None
    expulsion_vote: bool | None = None
    defense: str | None = None
    memory_update: str = ""
    strategy_summary: str = ""
    relationship_updates: dict[str, RelationshipDelta] = Field(default_factory=dict)

