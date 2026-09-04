"""Vera AI Bot — FastAPI application.

Exposes the 5 endpoints required by the magicpin AI Challenge judge:
  GET  /v1/healthz    — liveness probe
  GET  /v1/metadata   — team identity
  POST /v1/context    — receive category/merchant/customer/trigger data
  POST /v1/tick       — periodic wake-up, compose proactive messages
  POST /v1/reply      — handle merchant/customer replies
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

import composer
import config
from context_store import ContextStore
from ui import HTML_CONTENT
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


# ── Seed Data Loader ───────────────────────────────────────────────
def load_seed_data(store_instance: ContextStore) -> dict:
    """Load canonical challenge dataset files into memory store."""
    data_dir = Path(__file__).parent / "data"
    if not data_dir.exists():
        return {"loaded": False, "reason": "data directory not found"}

    counts = {"categories": 0, "merchants": 0, "customers": 0, "triggers": 0}

    # 1. Categories
    cat_dir = data_dir / "categories"
    if cat_dir.exists():
        for cat_file in cat_dir.glob("*.json"):
            slug = cat_file.stem
            try:
                with open(cat_file, "r", encoding="utf-8") as f:
                    cat_data = json.load(f)
                store_instance.upsert("category", slug, 1, cat_data)
                counts["categories"] += 1
            except Exception as e:
                logger.warning(f"Failed to load category {cat_file}: {e}")

    # 2. Merchants
    mx_file = data_dir / "merchants_seed.json"
    if mx_file.exists():
        try:
            with open(mx_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            merchants = data.get("merchants", data if isinstance(data, list) else [])
            for m in merchants:
                mid = m.get("merchant_id")
                if mid:
                    store_instance.upsert("merchant", mid, 1, m)
                    counts["merchants"] += 1
        except Exception as e:
            logger.warning(f"Failed to load merchants: {e}")

    # 3. Customers
    cx_file = data_dir / "customers_seed.json"
    if cx_file.exists():
        try:
            with open(cx_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            customers = data.get("customers", data if isinstance(data, list) else [])
            for c in customers:
                cid = c.get("customer_id")
                if cid:
                    store_instance.upsert("customer", cid, 1, c)
                    counts["customers"] += 1
        except Exception as e:
            logger.warning(f"Failed to load customers: {e}")

    # 4. Triggers
    trg_file = data_dir / "triggers_seed.json"
    if trg_file.exists():
        try:
            with open(trg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            triggers = data.get("triggers", data if isinstance(data, list) else [])
            for t in triggers:
                tid = t.get("id", t.get("trigger_id"))
                if tid:
                    store_instance.upsert("trigger", tid, 1, t)
                    counts["triggers"] += 1
        except Exception as e:
            logger.warning(f"Failed to load triggers: {e}")

    logger.info(f"Loaded real dataset: {counts}")
    return {"loaded": True, "counts": counts}


# ── App & State ────────────────────────────────────────────────────
app = FastAPI(title="Vera AI Bot", version=config.BOT_VERSION)
store = ContextStore()
START_TIME = time.time()

# Auto-seed on startup so web UI has real data immediately
load_seed_data(store)


# ═══════════════════════════════════════════════════════════════════
# GET / (Interactive Web Console & WhatsApp Simulator)
# ═══════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
def root():
    """Interactive Merchant AI Console & Live WhatsApp Simulator."""
    return HTMLResponse(content=HTML_CONTENT)


# ═══════════════════════════════════════════════════════════════════
# GET /v1/state (Live Data for Console UI)
# ═══════════════════════════════════════════════════════════════════

@app.get("/v1/state")
def get_state() -> dict:
    """Return all currently loaded real merchants, categories, and telemetry."""
    return {
        "counts": store.counts(),
        "merchants": store.get_all("merchant"),
        "categories": store.get_all("category"),
        "triggers": store.get_all("trigger"),
        "conversations": store.get_all_conversations(),
        "uptime_seconds": int(time.time() - START_TIME),
    }


@app.post("/v1/load-seed")
def load_seed() -> dict:
    """Load canonical challenge seed datasets into memory store."""
    return load_seed_data(store)


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
# POST /v1/tick (Parallelized with ThreadPoolExecutor)
# ═══════════════════════════════════════════════════════════════════

def _process_single_trigger(trigger_id: str) -> Optional[TickAction]:
    """Process a single trigger and return a TickAction, or None if skipped/failed."""
    # Look up the trigger
    trigger = store.get("trigger", trigger_id)
    if not trigger:
        logger.warning(f"Trigger not found in store: {trigger_id}")
        return None

    # Check suppression
    suppression_key = trigger.get("suppression_key", "")
    if suppression_key and store.is_suppressed(suppression_key):
        logger.info(f"Trigger suppressed: {trigger_id} ({suppression_key})")
        return None

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

    # Build conversation ID early (needed for anti-repetition)
    conv_parts = ["conv"]
    if merchant_id:
        conv_parts.append(merchant_id.replace("m_", ""))
    if customer_id:
        conv_parts.append(customer_id.replace("c_", ""))
    trigger_kind = trigger.get("kind", "msg")
    conv_parts.append(trigger_kind)
    conversation_id = "_".join(conv_parts)

    # Compose the message
    try:
        result = composer.compose(
            category=category,
            merchant=merchant,
            trigger=trigger,
            customer=customer,
            conversation_id=conversation_id,
        )
    except Exception as e:
        logger.error(f"Compose failed for {trigger_id}: {e}")
        return None

    body = result.get("body", "")
    if not body:
        logger.warning(f"Empty body for trigger {trigger_id}, skipping")
        return None

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

    # Mark as suppressed so we don't re-send in the same session
    if suppression_key:
        store.suppress(suppression_key)

    # Track conversation
    store.add_conversation_turn(conversation_id, "vera", body, turn=1)

    logger.info(
        f"Action composed: {trigger_id} → {merchant_id}"
        f" | cta={action.cta} | len={len(body)}"
    )
    return action


@app.post("/v1/tick")
def tick(req: TickRequest) -> dict:
    valid_triggers = req.available_triggers[:config.MAX_ACTIONS_PER_TICK]
    actions: List[TickAction] = []

    if not valid_triggers:
        return TickResponse(actions=[]).model_dump()

    # Execute composition in parallel to stay well within the 30s timeout cap
    workers = min(len(valid_triggers), 8)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_process_single_trigger, tid) for tid in valid_triggers]
        for future in futures:
            try:
                action = future.result()
                if action:
                    actions.append(action)
            except Exception as e:
                logger.error(f"Error processing trigger: {e}")

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
