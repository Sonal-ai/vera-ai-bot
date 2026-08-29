"""Vera AI Bot — FastAPI application.

Exposes the 5 endpoints required by the magicpin AI Challenge judge:
  GET  /v1/healthz    — liveness probe
  GET  /v1/metadata   — team identity
  POST /v1/context    — receive category/merchant/customer/trigger data
  POST /v1/tick       — periodic wake-up, compose proactive messages
  POST /v1/reply      — handle merchant/customer replies
"""

from __future__ import annotations

import logging
import time
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

import composer
import config
from context_store import ContextStore
from models import (
    ContextRequest,
    ContextResponse,
    HealthResponse,
    MetadataResponse,
    ReplyRequest,
    ReplyResponse,
    TickAction,
    TickRequest,
    TickResponse,
)

# ── Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("vera.main")

# ── App & State ────────────────────────────────────────────────────
app = FastAPI(title="Vera AI Bot", version=config.BOT_VERSION)
store = ContextStore()
START_TIME = time.time()


# ═══════════════════════════════════════════════════════════════════
# GET /v1/healthz
# ═══════════════════════════════════════════════════════════════════

@app.get("/v1/healthz")
def healthz() -> dict:
    return HealthResponse(
        status="ok",
        uptime_seconds=int(time.time() - START_TIME),
        contexts_loaded=store.counts(),
    ).model_dump()


# ═══════════════════════════════════════════════════════════════════
# GET /v1/metadata
# ═══════════════════════════════════════════════════════════════════

@app.get("/v1/metadata")
def metadata() -> dict:
    return MetadataResponse(
        team_name=config.TEAM_NAME,
        team_members=config.TEAM_MEMBERS,
        model=config.MODEL_NAME,
        approach=config.APPROACH,
        version=config.BOT_VERSION,
    ).model_dump()


# ═══════════════════════════════════════════════════════════════════
# POST /v1/context
# ═══════════════════════════════════════════════════════════════════

@app.post("/v1/context")
def receive_context(req: ContextRequest) -> JSONResponse:
    # Validate scope
    if req.scope not in ("category", "merchant", "customer", "trigger"):
        return JSONResponse(
            status_code=400,
            content=ContextResponse(
                accepted=False,
                reason="invalid_scope",
                details=f"Unknown scope: {req.scope}",
            ).model_dump(),
        )

    accepted, ack_id, current_version = store.upsert(
        scope=req.scope,
        context_id=req.context_id,
        version=req.version,
        payload=req.payload,
    )

    if not accepted:
        # Version conflict (stale)
        return JSONResponse(
            status_code=409,
            content=ContextResponse(
                accepted=False,
                reason="stale_version",
                current_version=current_version,
            ).model_dump(),
        )

    logger.info(f"Context stored: {req.scope}/{req.context_id} v{req.version}")
    return JSONResponse(
        status_code=200,
        content=ContextResponse(
            accepted=True,
            ack_id=ack_id,
            stored_at=store.get(req.scope, req.context_id) and ack_id,
        ).model_dump(),
    )


# ═══════════════════════════════════════════════════════════════════
# POST /v1/tick
# ═══════════════════════════════════════════════════════════════════

@app.post("/v1/tick")
def tick(req: TickRequest) -> dict:
    actions: List[TickAction] = []

    for trigger_id in req.available_triggers:
        if len(actions) >= config.MAX_ACTIONS_PER_TICK:
            break

        # Look up the trigger
        trigger = store.get("trigger", trigger_id)
        if not trigger:
            logger.warning(f"Trigger not found in store: {trigger_id}")
            continue

        # Check suppression
        suppression_key = trigger.get("suppression_key", "")
        if store.is_suppressed(suppression_key):
            logger.info(f"Trigger suppressed: {trigger_id} ({suppression_key})")
            continue

        # Resolve merchant
        merchant_id = trigger.get("merchant_id")
        merchant = store.get("merchant", merchant_id) if merchant_id else None

        # Resolve customer (for customer-scoped triggers)
        customer_id = trigger.get("customer_id")
        customer = store.get("customer", customer_id) if customer_id else None

        # Resolve category
        category_slug = None
        if merchant:
            category_slug = merchant.get("category_slug")
        if not category_slug:
            # Try to infer from trigger ID (e.g. "trg_001_research_digest_dentists")
            for cat in ("dentists", "salons", "restaurants", "gyms", "pharmacies"):
                if cat in trigger_id.lower():
                    category_slug = cat
                    break
        category = store.get("category", category_slug) if category_slug else None

        # Compose the message
        try:
            result = composer.compose(
                category=category,
                merchant=merchant,
                trigger=trigger,
                customer=customer,
            )
        except Exception as e:
            logger.error(f"Compose failed for {trigger_id}: {e}")
            continue

        body = result.get("body", "")
        if not body:
            logger.warning(f"Empty body for trigger {trigger_id}, skipping")
            continue

        # Build a meaningful conversation ID
        conv_parts = ["conv"]
        if merchant_id:
            conv_parts.append(merchant_id.replace("m_", ""))
        if customer_id:
            conv_parts.append(customer_id.replace("c_", ""))
        trigger_kind = trigger.get("kind", "msg")
        conv_parts.append(trigger_kind)
        conversation_id = "_".join(conv_parts)

        # Determine send_as
        send_as = result.get("send_as", "vera")
        if customer and trigger.get("scope") == "customer":
            send_as = "merchant_on_behalf"

        # Build the action
        action = TickAction(
            conversation_id=conversation_id,
            merchant_id=merchant_id or "unknown",
            customer_id=customer_id,
            send_as=send_as,
            trigger_id=trigger_id,
            body=body,
            cta=result.get("cta", "open_ended"),
            suppression_key=result.get("suppression_key", suppression_key),
            rationale=result.get("rationale", f"Trigger: {trigger_kind}"),
        )
        actions.append(action)

        # Mark as suppressed so we don't re-send in the same session
        if suppression_key:
            store.suppress(suppression_key)

        # Track conversation
        store.add_conversation_turn(conversation_id, "vera", body, turn=1)

        logger.info(
            f"Action composed: {trigger_id} → {merchant_id}"
            f" | cta={action.cta} | len={len(body)}"
        )

    return TickResponse(actions=actions).model_dump()


# ═══════════════════════════════════════════════════════════════════
# POST /v1/reply
# ═══════════════════════════════════════════════════════════════════

@app.post("/v1/reply")
def reply(req: ReplyRequest) -> dict:
    # Track the incoming message
    store.add_conversation_turn(
        req.conversation_id, req.from_role, req.message, turn=req.turn_number
    )

    # Look up merchant context for grounding
    merchant = store.get("merchant", req.merchant_id)

    # Look up category for voice
    category = None
    if merchant:
        category_slug = merchant.get("category_slug")
        if category_slug:
            category = store.get("category", category_slug)

    # Get conversation history
    conversation_history = store.get_conversation(req.conversation_id)

    # Handle the reply
    result = composer.handle_reply(
        conversation_history=conversation_history,
        from_role=req.from_role,
        message=req.message,
        turn_number=req.turn_number,
        merchant=merchant,
        category=category,
    )

    action = result.get("action", "send")
    response_data: dict = {
        "action": action,
        "rationale": result.get("rationale", "Contextual response"),
    }

    if action == "send":
        body = result.get("body", "")
        response_data["body"] = body
        response_data["cta"] = result.get("cta", "open_ended")
        # Track our response
        store.add_conversation_turn(
            req.conversation_id, "vera", body, turn=req.turn_number + 1
        )
    elif action == "wait":
        response_data["wait_seconds"] = result.get("wait_seconds", 1800)
    # action == "end" needs no extra fields

    logger.info(
        f"Reply handled: {req.conversation_id} turn {req.turn_number}"
        f" → action={action}"
    )
    return response_data


# ═══════════════════════════════════════════════════════════════════
# Entrypoint
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Vera Bot v{config.BOT_VERSION} on {config.HOST}:{config.PORT}")
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        log_level="info",
    )
