"""Pydantic models matching the magicpin AI Challenge HTTP contract."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════
# POST /v1/context
# ═══════════════════════════════════════════════════════════════════

class ContextRequest(BaseModel):
    scope: Literal["category", "merchant", "customer", "trigger"]
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: str


class ContextResponse(BaseModel):
    accepted: bool
    ack_id: Optional[str] = None
    stored_at: Optional[str] = None
    reason: Optional[str] = None
    current_version: Optional[int] = None
    details: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# POST /v1/tick
# ═══════════════════════════════════════════════════════════════════

class TickRequest(BaseModel):
    now: str
    available_triggers: List[str] = Field(default_factory=list)


class TickAction(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    send_as: Literal["vera", "merchant_on_behalf"] = "vera"
    trigger_id: str
    template_name: Optional[str] = None
    template_params: Optional[List[str]] = None
    body: str
    cta: Literal[
        "open_ended",
        "binary_yes_no",
        "binary_confirm_cancel",
        "multi_choice_slot",
        "none",
    ] = "open_ended"
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    actions: List[TickAction] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# POST /v1/reply
# ═══════════════════════════════════════════════════════════════════

class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    from_role: Literal["merchant", "customer"]
    message: str
    received_at: str
    turn_number: int


class ReplyResponse(BaseModel):
    action: Literal["send", "wait", "end"]
    body: Optional[str] = None
    cta: Optional[Literal[
        "open_ended",
        "binary_yes_no",
        "binary_confirm_cancel",
        "multi_choice_slot",
        "none",
    ]] = None
    wait_seconds: Optional[int] = None
    rationale: str


# ═══════════════════════════════════════════════════════════════════
# GET /v1/healthz
# ═══════════════════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    status: str = "ok"
    uptime_seconds: int = 0
    contexts_loaded: Dict[str, int] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
# GET /v1/metadata
# ═══════════════════════════════════════════════════════════════════

class MetadataResponse(BaseModel):
    team_name: str
    team_members: List[str]
    model: str
    approach: str
    contact_email: Optional[str] = None
    version: str
    submitted_at: Optional[str] = None
