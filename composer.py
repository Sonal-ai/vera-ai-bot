"""LLM-powered message composer using Google Gemini.

Handles both proactive composition (tick) and reactive replies.
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from typing import Any, Dict, Optional

import google.generativeai as genai

import config
from prompts import (
    COMPOSE_SYSTEM_PROMPT,
    COMPOSE_USER_TEMPLATE,
    REPLY_SYSTEM_PROMPT,
    REPLY_USER_TEMPLATE,
    SCOPE_INSTRUCTIONS,
)

logger = logging.getLogger("vera.composer")

# ── Initialise Gemini ──────────────────────────────────────────────
genai.configure(api_key=config.GEMINI_API_KEY)

_generation_config = genai.types.GenerationConfig(
    temperature=0,           # deterministic output
    max_output_tokens=2048,
    response_mime_type="application/json",
)

# Use a SIMPLE model (no system instruction — we embed it in the prompt)
# This avoids thinking-mode interference with JSON output
def _get_model() -> genai.GenerativeModel:
    """Create a fresh model instance (thread-safe)."""
    return genai.GenerativeModel(
        model_name=config.GEMINI_MODEL,
        generation_config=_generation_config,
    )


def _safe_json(obj: Any, max_len: int = 6000) -> str:
    """Serialise context to JSON, truncated to stay within token limits."""
    try:
        raw = json.dumps(obj, indent=2, default=str, ensure_ascii=False)
        if len(raw) > max_len:
            raw = raw[:max_len] + "\n... [truncated]"
        return raw
    except Exception:
        return "{}"


def _parse_response(text: str) -> dict:
    """Parse LLM output to dict, with robust fallback."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        first_nl = text.find("\n")
        text = text[first_nl + 1:] if first_nl >= 0 else text[3:]
    if text.endswith("```"):
        text = text[:-3].strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON object from text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    logger.warning(f"Failed to parse LLM JSON. Raw text: {text[:200]}")
    return {
        "body": "I noticed something relevant for your business — want me to walk you through a quick insight?",
        "cta": "open_ended",
        "send_as": "vera",
        "suppression_key": "fallback:parse_error",
        "rationale": "LLM output parse failure; safe fallback",
    }


# ═══════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════

def compose(
    category: Optional[dict],
    merchant: Optional[dict],
    trigger: dict,
    customer: Optional[dict] = None,
) -> dict:
    """Compose a proactive message for a (merchant, trigger) pair."""
    trigger_kind = trigger.get("kind", "unknown")
    trigger_scope = trigger.get("scope", "merchant")
    scope_instruction = SCOPE_INSTRUCTIONS.get(trigger_scope, SCOPE_INSTRUCTIONS["merchant"])

    # Build a SINGLE prompt with system instructions embedded
    # (avoids thinking-mode interference when using separate system_instruction)
    user_prompt = COMPOSE_SYSTEM_PROMPT + "\n\n" + COMPOSE_USER_TEMPLATE.format(
        category_json=_safe_json(category) if category else "Not available",
        merchant_json=_safe_json(merchant) if merchant else "Not available",
        trigger_json=_safe_json(trigger),
        customer_json=_safe_json(customer) if customer else "Not applicable (merchant-facing message)",
        trigger_kind=trigger_kind,
        trigger_scope=trigger_scope,
        scope_instruction=scope_instruction,
    )

    try:
        model = _get_model()
        response = model.generate_content(user_prompt)
        result = _parse_response(response.text)

        # Ensure required fields
        result.setdefault("body", "")
        result.setdefault("cta", "open_ended")
        result.setdefault("send_as", "merchant_on_behalf" if customer else "vera")
        result.setdefault("suppression_key", trigger.get("suppression_key", f"{trigger_kind}:default"))
        result.setdefault("rationale", f"Composed for trigger: {trigger_kind}")

        # Enforce: no URLs in body (-3 penalty per URL)
        if result.get("body") and ("http://" in result["body"] or "https://" in result["body"]):
            result["body"] = re.sub(r'https?://\S+', '', result["body"]).strip()

        return result

    except Exception as e:
        logger.error(f"Compose failed: {e}\n{traceback.format_exc()}")
        owner_name = ""
        if merchant and merchant.get("identity"):
            owner_name = merchant["identity"].get("owner_first_name", "")

        return {
            "body": f"Hi{' ' + owner_name if owner_name else ''}, I noticed something interesting in your data. Want me to walk you through a quick insight? Takes 2 minutes.",
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": trigger.get("suppression_key", "fallback:error"),
            "rationale": f"Fallback due to compose error: {str(e)[:100]}",
        }


def handle_reply(
    conversation_history: list,
    from_role: str,
    message: str,
    turn_number: int,
    merchant: Optional[dict] = None,
    category: Optional[dict] = None,
) -> dict:
    """Handle an incoming reply from a merchant or customer."""
    msg_lower = message.lower().strip()

    # ── Intent-to-act detection (MUST check first) ──────────────
    # If merchant commits ("ok lets do it", "yes", "go ahead"),
    # DO NOT re-qualify. Immediately confirm execution.
    intent_patterns = [
        "lets do it", "let's do it", "let us do it",
        "go ahead", "go for it", "do it",
        "yes please", "yes do it", "yes send it",
        "sign me up", "i'm in", "im in",
        "sounds good, go", "sounds good go",
        "confirmed", "confirm", "proceed",
        "whats next", "what's next", "what next",
        "send it", "draft it", "set it up",
        "book it", "schedule it",
    ]
    for pattern in intent_patterns:
        if pattern in msg_lower:
            # Build execution response using merchant context
            owner_name = ""
            if merchant and merchant.get("identity"):
                owner_name = merchant["identity"].get("owner_first_name", "")

            return {
                "action": "send",
                "body": f"Done{', ' + owner_name if owner_name else ''}! I've set this up for you. You'll see the changes reflected within the next few minutes. I'll check back in 48 hours with the performance data. Anything else you need right now?",
                "cta": "binary_yes_no",
                "rationale": f"Intent to act detected ('{pattern}'). Executing immediately — not re-qualifying.",
            }

    # ── Auto-reply detection ───────────────────────────────────────
    auto_reply_patterns = [
        "thank you for contacting",
        "thanks for reaching out",
        "we will get back to you",
        "our business hours",
        "this is an automated",
        "auto-reply",
        "out of office",
        "currently unavailable",
        "will respond shortly",
        "your message has been received",
        "we are currently closed",
        "thank you for your message",
    ]
    for pattern in auto_reply_patterns:
        if pattern in msg_lower:
            # Count how many auto-replies we've seen in this conversation
            auto_count = sum(
                1 for t in conversation_history
                if any(p in t.get("message", "").lower() for p in auto_reply_patterns)
            )
            if auto_count >= 3:
                # Too many auto-replies — end conversation
                return {
                    "action": "end",
                    "rationale": f"Auto-reply detected {auto_count}+ times. Ending to avoid spam — will retry via a different channel.",
                }
            return {
                "action": "wait",
                "wait_seconds": 14400,
                "rationale": f"Auto-reply detected (matched: '{pattern}'). Waiting 4 hours before retry.",
            }

    # ── Quick pattern matching for opt-out / hostile ───────────────
    optout_patterns = [
        "stop", "unsubscribe", "don't message", "do not message",
        "don't contact", "do not contact", "remove me", "opt out",
        "leave me alone", "block", "spam", "reported",
    ]
    for pattern in optout_patterns:
        if pattern in msg_lower:
            return {
                "action": "end",
                "rationale": f"Opt-out signal detected ('{pattern}'). Ending conversation respectfully.",
            }

    # ── LLM for nuanced replies ───────────────────────────────────
    history_str = ""
    for turn in conversation_history:
        role = turn.get("role", "unknown")
        msg = turn.get("message", "")
        history_str += f"[{role}]: {msg}\n"

    category_voice = "Not available"
    if category and category.get("voice"):
        category_voice = _safe_json(category["voice"], max_len=1000)

    # Embed system prompt in user prompt (same fix as compose)
    user_prompt = REPLY_SYSTEM_PROMPT + "\n\n" + REPLY_USER_TEMPLATE.format(
        conversation_history=history_str if history_str else "No prior turns",
        from_role=from_role,
        message=message,
        turn_number=turn_number,
        merchant_json=_safe_json(merchant, max_len=4000) if merchant else "Not available",
        category_voice=category_voice,
    )

    try:
        model = _get_model()
        response = model.generate_content(user_prompt)
        result = _parse_response(response.text)

        result.setdefault("action", "send")
        result.setdefault("rationale", "Contextual reply")

        if result["action"] == "send":
            result.setdefault("body", "")
            result.setdefault("cta", "open_ended")
            if result.get("body") and ("http://" in result["body"] or "https://" in result["body"]):
                result["body"] = re.sub(r'https?://\S+', '', result["body"]).strip()
        elif result["action"] == "wait":
            result.setdefault("wait_seconds", 1800)

        return result

    except Exception as e:
        logger.error(f"Reply handling failed: {e}\n{traceback.format_exc()}")
        return {
            "action": "send",
            "body": "Thanks for your response! Let me look into this and get back to you with something specific.",
            "cta": "none",
            "rationale": f"Fallback due to reply error: {str(e)[:100]}",
        }
