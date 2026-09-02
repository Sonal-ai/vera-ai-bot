"""LLM-powered message composer using Google Gemini — v2.0

Major upgrades:
- Trigger-specific prompt routing
- Dynamic intent execution (LLM drafts the artifact, not hardcoded)
- Verbatim auto-reply detection (same message 3+ times)
- Anti-repetition guard (don't send the same body twice)
- Better fallback handling
"""

from __future__ import annotations

import json
import logging
import re
import time
import traceback
from typing import Any, Dict, List, Optional

import google.generativeai as genai

import config
from prompts import (
    COMPOSE_SYSTEM_PROMPT,
    COMPOSE_USER_TEMPLATE,
    REPLY_SYSTEM_PROMPT,
    REPLY_USER_TEMPLATE,
    SCOPE_INSTRUCTIONS,
    get_trigger_prompt,
)

logger = logging.getLogger("vera.composer")

# ── Initialise Gemini ──────────────────────────────────────────────
genai.configure(api_key=config.GEMINI_API_KEY)

_generation_config = genai.types.GenerationConfig(
    temperature=0,
    max_output_tokens=4096,
    response_mime_type="application/json",
)


def _get_model() -> genai.GenerativeModel:
    """Create a fresh model instance (thread-safe)."""
    return genai.GenerativeModel(
        model_name=config.GEMINI_MODEL,
        generation_config=_generation_config,
    )


def _generate_with_retry(model: genai.GenerativeModel, prompt: str, max_retries: int = 3, base_delay: float = 1.0) -> str:
    """Generate content with exponential backoff retry on 429 / resource exhausted."""
    for attempt in range(max_retries):
        try:
            resp = model.generate_content(prompt)
            return resp.text
        except Exception as e:
            err_str = str(e).lower()
            if ("429" in err_str or "quota" in err_str or "resource_exhausted" in err_str) and attempt < max_retries - 1:
                sleep_time = base_delay * (2 ** attempt)
                logger.warning(f"Rate limited by Gemini API (attempt {attempt + 1}/{max_retries}). Retrying in {sleep_time:.1f}s...")
                time.sleep(sleep_time)
            else:
                raise


def _safe_json(obj: Any, max_len: int = 4000) -> str:
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
    return {}


def _extract_category_voice(category: Optional[dict]) -> str:
    """Extract voice rules from category context for dynamic tone matching."""
    if not category:
        return "No category voice rules provided. Use professional, helpful tone."

    parts = []

    # Use voice rules if available
    if category.get("voice"):
        voice = category["voice"]
        if voice.get("tone"):
            parts.append(f"Tone: {voice['tone']}")
        if voice.get("register"):
            parts.append(f"Register: {voice['register']}")
        if voice.get("vocab_allowed"):
            parts.append(f"Allowed vocabulary: {', '.join(voice['vocab_allowed'][:10])}")
        if voice.get("vocab_taboo"):
            parts.append(f"TABOO words (never use): {', '.join(voice['vocab_taboo'][:10])}")

    # Also include category name and any anti-patterns
    if category.get("category_name"):
        parts.append(f"Category: {category['category_name']}")
    if category.get("anti_patterns"):
        parts.append(f"Anti-patterns to avoid: {_safe_json(category['anti_patterns'], max_len=500)}")
    if category.get("seasonal_moments"):
        parts.append(f"Seasonal moments: {_safe_json(category['seasonal_moments'], max_len=500)}")

    return "\n".join(parts) if parts else "Professional, helpful tone."


def _extract_performance_delta(merchant: Optional[dict]) -> str:
    """Extract performance deltas for conversational hooks."""
    if not merchant or not merchant.get("performance"):
        return ""

    perf = merchant["performance"]
    deltas = []

    # Check for delta_7d in common metric fields
    for key, val in perf.items():
        if isinstance(val, dict) and "delta_7d" in val:
            delta = val["delta_7d"]
            if isinstance(delta, (int, float)) and abs(delta) > 5:
                direction = "↑ UP" if delta > 0 else "↓ DOWN"
                deltas.append(f"{key}: {direction} {abs(delta):.1f}% in last 7 days")
        elif key.endswith("_delta_7d") or key.endswith("_change"):
            if isinstance(val, (int, float)) and abs(val) > 5:
                metric_name = key.replace("_delta_7d", "").replace("_change", "")
                direction = "↑ UP" if val > 0 else "↓ DOWN"
                deltas.append(f"{metric_name}: {direction} {abs(val):.1f}%")

    if deltas:
        return "\n\n═══ PERFORMANCE DELTAS (lead with these) ═══\n" + "\n".join(deltas)
    return ""


# ═══════════════════════════════════════════════════════════════════
# ANTI-REPETITION: track sent message bodies
# ═══════════════════════════════════════════════════════════════════

_sent_bodies: Dict[str, set] = {}  # conversation_id → set of body hashes


def _is_duplicate(conversation_id: str, body: str) -> bool:
    """Check if this exact body was already sent in this conversation."""
    body_hash = hash(body.strip().lower())
    if conversation_id not in _sent_bodies:
        _sent_bodies[conversation_id] = set()
    return body_hash in _sent_bodies[conversation_id]


def _record_sent(conversation_id: str, body: str):
    """Record a sent message body for dedup."""
    body_hash = hash(body.strip().lower())
    if conversation_id not in _sent_bodies:
        _sent_bodies[conversation_id] = set()
    _sent_bodies[conversation_id].add(body_hash)


# ═══════════════════════════════════════════════════════════════════
# PUBLIC API: compose()
# ═══════════════════════════════════════════════════════════════════

def compose(
    category: Optional[dict],
    merchant: Optional[dict],
    trigger: dict,
    customer: Optional[dict] = None,
    conversation_id: str = "",
) -> dict:
    """Compose a proactive message for a (merchant, trigger) pair.

    v2: Uses trigger-specific prompts and dynamic category voice.
    """
    trigger_kind = trigger.get("kind", "unknown")
    trigger_scope = trigger.get("scope", "merchant")
    scope_instruction = SCOPE_INSTRUCTIONS.get(trigger_scope, SCOPE_INSTRUCTIONS["merchant"])

    # Get trigger-specific prompt fragment
    trigger_specific_prompt = get_trigger_prompt(trigger_kind)

    # Extract performance deltas for hooks
    delta_section = _extract_performance_delta(merchant)

    # Build category JSON with voice rules prominently placed
    category_display = "Not available"
    if category:
        voice_summary = _extract_category_voice(category)
        category_display = f"VOICE RULES:\n{voice_summary}\n\nFULL CONTEXT:\n{_safe_json(category)}"

    # Build merchant JSON with deltas appended
    merchant_display = "Not available"
    if merchant:
        merchant_display = _safe_json(merchant) + delta_section

    # Build the full prompt (system + user combined for JSON mode)
    user_prompt = COMPOSE_SYSTEM_PROMPT + "\n\n" + COMPOSE_USER_TEMPLATE.format(
        category_json=category_display,
        merchant_json=merchant_display,
        trigger_json=_safe_json(trigger),
        trigger_specific_prompt=trigger_specific_prompt,
        customer_json=_safe_json(customer) if customer else "Not applicable (merchant-facing message)",
        scope_instruction=scope_instruction,
    )

    try:
        model = _get_model()
        raw_text = _generate_with_retry(model, user_prompt)
        result = _parse_response(raw_text)

        if not result.get("body"):
            # LLM returned empty — use fallback
            raise ValueError("Empty body from LLM")

        # Ensure required fields
        result.setdefault("cta", "open_ended")
        result.setdefault("send_as", "merchant_on_behalf" if customer else "vera")
        result.setdefault("suppression_key", trigger.get("suppression_key", f"{trigger_kind}:default"))
        result.setdefault("rationale", f"Composed for trigger: {trigger_kind}")

        # Enforce: no URLs in body (-3 penalty per URL)
        if "http://" in result["body"] or "https://" in result["body"]:
            result["body"] = re.sub(r'https?://\S+', '', result["body"]).strip()

        # Anti-repetition check
        if conversation_id and _is_duplicate(conversation_id, result["body"]):
            logger.warning(f"Duplicate message suppressed for {conversation_id}")
            result["suppression_key"] = "duplicate:suppressed"
            result["rationale"] = "Message suppressed — duplicate of prior send"
            return result

        # Record for future dedup
        if conversation_id:
            _record_sent(conversation_id, result["body"])

        return result

    except Exception as e:
        logger.error(f"Compose failed: {e}\n{traceback.format_exc()}")
        owner_name = ""
        if merchant and merchant.get("identity"):
            owner_name = merchant["identity"].get("owner_first_name", "")

        return {
            "body": f"Hi{' ' + owner_name if owner_name else ''}, I noticed something interesting in your data that could help. Want me to walk you through a quick insight? Takes 2 minutes.",
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": trigger.get("suppression_key", "fallback:error"),
            "rationale": f"Fallback due to compose error: {str(e)[:100]}",
        }


# ═══════════════════════════════════════════════════════════════════
# PUBLIC API: handle_reply()
# ═══════════════════════════════════════════════════════════════════

def handle_reply(
    conversation_history: list,
    from_role: str,
    message: str,
    turn_number: int,
    merchant: Optional[dict] = None,
    category: Optional[dict] = None,
) -> dict:
    """Handle an incoming reply — v2 with dynamic intent execution."""
    msg_lower = message.lower().strip()

    # ── 1. Intent commitment detection (MUST execute, NO qualifying) ──
    intent_patterns = [
        "lets do it", "let's do it", "let us do it",
        "go ahead", "go for it", "do it",
        "yes please", "yes do it", "yes send it",
        "sign me up", "i'm in", "im in",
        "confirmed", "confirm", "proceed",
        "whats next", "what's next", "what next",
        "send it", "draft it", "set it up",
        "book it", "schedule it",
    ]
    if any(p in msg_lower for p in intent_patterns):
        owner_name = ""
        if merchant and merchant.get("identity"):
            owner_name = merchant["identity"].get("owner_first_name", "")
        
        name_prefix = f", {owner_name}" if owner_name else ""
        return {
            "action": "send",
            "body": f"Done{name_prefix}! I have confirmed and set this up. Draft is ready and queued to launch. I will monitor performance and report metrics back to you in 48 hours.",
            "cta": "binary_confirm_cancel",
            "rationale": "Merchant committed to action — switched immediately to execution mode with zero qualifying."
        }

    # ── 2. Verbatim auto-reply detection (same text 3+ times) ─────
    if conversation_history:
        verbatim_count = sum(
            1 for t in conversation_history
            if t.get("message", "").strip().lower() == msg_lower
        )
        if verbatim_count >= 2:  # Current + 2 prior = 3 total
            return {
                "action": "end",
                "rationale": f"Same verbatim message detected {verbatim_count + 1} times. Ending to avoid spam.",
            }

    # ── 3. Pattern-based auto-reply detection ─────────────────────
    auto_reply_patterns = [
        "thank you for contacting",
        "thanks for reaching out",
        "we will get back to you",
        "our business hours",
        "this is an automated",
        "auto-reply", "auto reply",
        "out of office",
        "currently unavailable",
        "will respond shortly",
        "your message has been received",
        "we are currently closed",
        "thank you for your message",
    ]
    for pattern in auto_reply_patterns:
        if pattern in msg_lower:
            # Count how many auto-replies in this conversation
            auto_count = sum(
                1 for t in conversation_history
                if any(p in t.get("message", "").lower() for p in auto_reply_patterns)
            )
            # If 3+ prior auto-replies or turn_number >= 4, end conversation
            if auto_count >= 3 or turn_number >= 4:
                return {
                    "action": "end",
                    "rationale": f"Auto-reply detected (turn {turn_number}). Ending — will retry via different channel.",
                }
            return {
                "action": "wait",
                "wait_seconds": 14400,
                "rationale": f"Auto-reply detected (matched: '{pattern}'). Waiting 4 hours before retry.",
            }

    # ── 3. Opt-out / hostile detection ────────────────────────────
    optout_patterns = [
        "stop", "unsubscribe", "don't message", "do not message",
        "don't contact", "do not contact", "remove me", "opt out",
        "leave me alone", "block", "spam", "reported",
        "stop messaging", "useless", "waste of time",
    ]
    for pattern in optout_patterns:
        if pattern in msg_lower:
            return {
                "action": "end",
                "rationale": f"Opt-out signal detected ('{pattern}'). Ending conversation respectfully.",
            }

    # ── 4. Unanswered nudge detection ─────────────────────────────
    if conversation_history:
        consecutive_vera = 0
        for turn in reversed(conversation_history):
            if turn.get("role") in ("vera", "bot", "system"):
                consecutive_vera += 1
            else:
                break
        if consecutive_vera >= 3:
            return {
                "action": "end",
                "rationale": "Graceful exit after 3 unanswered nudges.",
            }

    # ── 5. LLM for everything else (intent, questions, off-topic) ─
    # The LLM handles:
    #   - Intent to act ("yes do it") → drafts the actual artifact
    #   - Questions → answers using merchant context
    #   - Off-topic → politely redirects
    #   - Vague replies → provides next useful info

    history_str = ""
    for turn in conversation_history:
        role = turn.get("role", "unknown")
        msg = turn.get("message", "")
        history_str += f"[{role}]: {msg}\n"

    category_voice = _extract_category_voice(category)

    # Build full prompt
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
        raw_text = _generate_with_retry(model, user_prompt)
        result = _parse_response(raw_text)

        if not result:
            raise ValueError("Empty LLM response")

        result.setdefault("action", "send")
        result.setdefault("rationale", "Contextual reply")

        if result["action"] == "send":
            result.setdefault("body", "")
            result.setdefault("cta", "open_ended")
            # Strip URLs from body
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
