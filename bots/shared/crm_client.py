"""
SHARED CRM CLIENT — Single source of truth for CRM operations
═══════════════════════════════════════════════════════════════
Master Bot Upgrade Directive — Phase 7 (CRM Unification).

Every bot that touches CRM data must use this client.
Connects to local Wholesale CRM at http://localhost:5050.

Provides:
  • Property CRUD with auto-dedup
  • Buyer matching
  • Activity logging (every material action)
  • Task creation (next-step queue)
  • Status updates using shared Status enum
  • Health check + graceful fallback
"""
import json
import requests
from datetime import datetime
from typing import Any, Optional

from bots.shared.standards import Status, log, save_state, STATE_DIR
import os

CRM_BASE = os.getenv("CRM_BASE_URL", "http://localhost:5050")
PENDING_QUEUE = os.path.join(STATE_DIR, "crm_pending_writeback.json")


class CRMClient:
    """Unified CRM client. All bots use this."""

    def __init__(self, base_url: str = CRM_BASE, timeout: int = 5):
        self.base = base_url
        self.timeout = timeout
        self._healthy: Optional[bool] = None

    # ── Health ───────────────────────────────────────────────────────────────
    def is_healthy(self) -> bool:
        """Check if CRM is reachable. Caches result for the session."""
        if self._healthy is not None:
            return self._healthy
        try:
            r = requests.get(f"{self.base}/api/health", timeout=self.timeout)
            self._healthy = r.ok
            return self._healthy
        except Exception:
            self._healthy = False
            return False

    # ── Properties ───────────────────────────────────────────────────────────
    def find_property(self, address: str) -> Optional[dict]:
        """Search for an existing property by address. Returns first match or None."""
        if not self.is_healthy():
            return None
        try:
            r = requests.get(
                f"{self.base}/api/properties/search",
                params={"address": address[:30]},
                timeout=self.timeout,
            )
            if r.ok:
                results = r.json()
                return results[0] if results else None
        except Exception as e:
            log.warning(f"CRM find_property failed: {e}")
        return None

    def upsert_property(self, data: dict) -> Optional[dict]:
        """
        Create or update a property. Auto-dedups by address.
        Returns CRM record dict or None on failure.
        """
        if not self.is_healthy():
            self._queue_writeback("upsert_property", data)
            return None

        existing = self.find_property(data.get("address", ""))

        try:
            if existing:
                # PATCH
                prop_id = existing["id"]
                r = requests.patch(
                    f"{self.base}/api/properties/{prop_id}",
                    json=data,
                    timeout=self.timeout,
                )
                if r.ok:
                    log.info(f"CRM patched property #{prop_id}")
                    return {**existing, **data, "id": prop_id, "_action": "updated"}
            else:
                # POST
                r = requests.post(
                    f"{self.base}/api/properties",
                    json=data,
                    timeout=self.timeout,
                )
                if r.ok:
                    new_id = r.json().get("id")
                    log.info(f"CRM created property #{new_id}")
                    return {**data, "id": new_id, "_action": "created"}
        except Exception as e:
            log.warning(f"CRM upsert_property failed: {e}")
            self._queue_writeback("upsert_property", data)
        return None

    def update_status(self, prop_id: int, status: str) -> bool:
        """Update property status. Accepts Status enum or string."""
        if isinstance(status, Status):
            status = status.value
        return self.update_property(prop_id, {"status": status})

    def update_property(self, prop_id: int, fields: dict) -> bool:
        if not self.is_healthy():
            self._queue_writeback("update_property", {"id": prop_id, **fields})
            return False
        try:
            r = requests.patch(
                f"{self.base}/api/properties/{prop_id}",
                json=fields,
                timeout=self.timeout,
            )
            return r.ok
        except Exception as e:
            log.warning(f"CRM update_property failed: {e}")
            return False

    # ── Buyers ───────────────────────────────────────────────────────────────
    def match_buyers(self, zip_code: str = "", prop_type: str = "", price: int = 0, limit: int = 5) -> list:
        """Get matched buyers ranked by fit score."""
        if not self.is_healthy():
            return []
        try:
            r = requests.get(
                f"{self.base}/api/buyers/match",
                params={"zip": zip_code, "type": prop_type, "price": price},
                timeout=self.timeout,
            )
            if r.ok:
                return r.json()[:limit]
        except Exception as e:
            log.warning(f"CRM match_buyers failed: {e}")
        return []

    def list_buyers(self) -> list:
        if not self.is_healthy():
            return []
        try:
            r = requests.get(f"{self.base}/api/buyers", timeout=self.timeout)
            return r.json() if r.ok else []
        except Exception:
            return []

    # ── Activities (audit log) ───────────────────────────────────────────────
    def log_activity(
        self,
        property_id: Optional[int] = None,
        buyer_id: Optional[int] = None,
        activity_type: str = "",
        summary: str = "",
        details: Any = None,
    ) -> bool:
        """Log a material action to the CRM audit trail."""
        payload = {
            "property_id": property_id,
            "buyer_id": buyer_id,
            "activity_type": activity_type,
            "summary": summary,
            "details": json.dumps(details) if details else "",
        }
        if not self.is_healthy():
            self._queue_writeback("activity", payload)
            return False
        try:
            r = requests.post(f"{self.base}/api/activities", json=payload, timeout=self.timeout)
            return r.ok
        except Exception as e:
            log.warning(f"CRM log_activity failed: {e}")
            self._queue_writeback("activity", payload)
            return False

    # ── Tasks ────────────────────────────────────────────────────────────────
    def create_task(
        self,
        task_type: str,
        description: str,
        property_id: Optional[int] = None,
        buyer_id: Optional[int] = None,
        priority: str = "medium",
        due_date: Optional[str] = None,
    ) -> bool:
        """Create a follow-up task in the CRM queue."""
        payload = {
            "task_type": task_type,
            "description": description,
            "property_id": property_id,
            "buyer_id": buyer_id,
            "priority": priority,
            "due_date": due_date,
        }
        if not self.is_healthy():
            self._queue_writeback("task", payload)
            return False
        try:
            r = requests.post(f"{self.base}/api/tasks", json=payload, timeout=self.timeout)
            return r.ok
        except Exception as e:
            log.warning(f"CRM create_task failed: {e}")
            self._queue_writeback("task", payload)
            return False

    # ── Stats ────────────────────────────────────────────────────────────────
    def get_stats(self) -> dict:
        if not self.is_healthy():
            return {}
        try:
            r = requests.get(f"{self.base}/api/stats", timeout=self.timeout)
            return r.json() if r.ok else {}
        except Exception:
            return {}

    # ── Failsafe queue (Phase 8: never lose work) ───────────────────────────
    def _queue_writeback(self, kind: str, payload: dict) -> None:
        """Queue a CRM write that failed for later retry."""
        try:
            queue = []
            if os.path.exists(PENDING_QUEUE):
                with open(PENDING_QUEUE) as f:
                    queue = json.load(f)
            queue.append({
                "kind": kind,
                "payload": payload,
                "queued_at": datetime.utcnow().isoformat(),
            })
            save_state(PENDING_QUEUE, queue[-500:])
            log.info(f"CRM writeback queued ({len(queue)} pending)")
        except Exception:
            pass

    def flush_pending(self) -> int:
        """Try to drain the pending queue. Returns number sent."""
        if not self.is_healthy() or not os.path.exists(PENDING_QUEUE):
            return 0
        try:
            with open(PENDING_QUEUE) as f:
                queue = json.load(f)
        except Exception:
            return 0

        sent = 0
        remaining = []
        for entry in queue:
            kind = entry["kind"]
            payload = entry["payload"]
            try:
                if kind == "upsert_property":
                    if self.upsert_property(payload):
                        sent += 1
                        continue
                elif kind == "activity":
                    if self.log_activity(**{k: payload.get(k) for k in ("property_id", "buyer_id", "activity_type", "summary", "details")}):
                        sent += 1
                        continue
                elif kind == "task":
                    if self.create_task(**payload):
                        sent += 1
                        continue
            except Exception:
                pass
            remaining.append(entry)

        save_state(PENDING_QUEUE, remaining)
        if sent:
            log.info(f"CRM flushed {sent} pending writes ({len(remaining)} still queued)")
        return sent


# Module-level singleton
crm = CRMClient()


__all__ = ["CRMClient", "crm"]
