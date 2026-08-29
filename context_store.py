"""Thread-safe, version-aware in-memory context store.

Stores the four context scopes (category, merchant, customer, trigger)
pushed by the judge via POST /v1/context.  Supports idempotent upserts
with version conflict detection and conversation history tracking.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


class ContextStore:
    """Singleton-style in-memory store for all four context scopes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {scope: {context_id: {"version": int, "payload": dict, "stored_at": str, "ack_id": str}}}
        self._store: Dict[str, Dict[str, Dict[str, Any]]] = {
            "category": {},
            "merchant": {},
            "customer": {},
            "trigger": {},
        }
        # Conversation history: {conversation_id: [{"role": str, "message": str, "turn": int}]}
        self._conversations: Dict[str, List[Dict[str, Any]]] = {}
        # Suppression keys already fired in this session
        self._suppressed: set[str] = set()

    # ── Context upsert with version checking ───────────────────────
    def upsert(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: dict,
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """Insert or update a context entry.

        Returns:
            (accepted, ack_id | None, current_version | None)
            - (True, ack_id, None) on success or idempotent re-post
            - (False, None, current_version) when the incoming version is stale
        """
        with self._lock:
            existing = self._store.get(scope, {}).get(context_id)

            if existing is not None:
                if version < existing["version"]:
                    # Stale — reject
                    return False, None, existing["version"]
                if version == existing["version"]:
                    # Idempotent no-op — return original ack
                    return True, existing["ack_id"], None

            # New entry or higher version — store
            now = datetime.now(timezone.utc).isoformat()
            ack_id = f"ack_{context_id}_v{version}"

            if scope not in self._store:
                self._store[scope] = {}

            self._store[scope][context_id] = {
                "version": version,
                "payload": payload,
                "stored_at": now,
                "ack_id": ack_id,
            }
            return True, ack_id, None

    # ── Lookups ────────────────────────────────────────────────────
    def get(self, scope: str, context_id: str) -> Optional[dict]:
        """Return the payload for a given (scope, context_id), or None."""
        with self._lock:
            entry = self._store.get(scope, {}).get(context_id)
            return dict(entry["payload"]) if entry else None

    def get_all(self, scope: str) -> Dict[str, dict]:
        """Return {context_id: payload} for every entry in a scope."""
        with self._lock:
            return {
                cid: dict(entry["payload"])
                for cid, entry in self._store.get(scope, {}).items()
            }

    def counts(self) -> Dict[str, int]:
        """Return {scope: count} for /v1/healthz."""
        with self._lock:
            return {scope: len(entries) for scope, entries in self._store.items()}

    # ── Conversation history ───────────────────────────────────────
    def add_conversation_turn(
        self, conv_id: str, role: str, message: str, turn: int = 0
    ) -> None:
        with self._lock:
            if conv_id not in self._conversations:
                self._conversations[conv_id] = []
            self._conversations[conv_id].append(
                {"role": role, "message": message, "turn": turn}
            )

    def get_conversation(self, conv_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._conversations.get(conv_id, []))

    # ── Suppression tracking ───────────────────────────────────────
    def is_suppressed(self, key: str) -> bool:
        if not key:
            return False
        with self._lock:
            return key in self._suppressed

    def suppress(self, key: str) -> None:
        if key:
            with self._lock:
                self._suppressed.add(key)

    # ── Helpers ────────────────────────────────────────────────────
    def find_merchants_by_category(self, category_slug: str) -> List[Dict[str, Any]]:
        """Return all merchant payloads whose category_slug matches."""
        with self._lock:
            results = []
            for entry in self._store.get("merchant", {}).values():
                payload = entry["payload"]
                if payload.get("category_slug") == category_slug:
                    results.append(dict(payload))
            return results

    def find_triggers_for_merchant(self, merchant_id: str) -> List[Dict[str, Any]]:
        """Return all trigger payloads targeting a specific merchant."""
        with self._lock:
            results = []
            for entry in self._store.get("trigger", {}).values():
                payload = entry["payload"]
                if payload.get("merchant_id") == merchant_id:
                    results.append(dict(payload))
            return results
