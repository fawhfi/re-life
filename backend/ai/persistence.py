"""Persistence ports and Supabase adapters for ReAgent conversations and memory."""
from __future__ import annotations

from typing import Any, Protocol

from backend.ai.workflow import AgentMemoryState, normalize_agent_language
from backend.storage import (
    supabase_delete,
    supabase_enabled,
    supabase_request,
    supabase_select,
    supabase_select_one,
)


class AgentConversationStore(Protocol):
    async def save(self, conversation: dict[str, Any]) -> None: ...

    async def list(self, user_id: int) -> list[dict[str, Any]]: ...

    async def get(
        self,
        user_id: int,
        conversation_id: str,
    ) -> dict[str, Any] | None: ...

    async def delete(self, user_id: int, conversation_id: str) -> bool: ...


class AgentMemoryStore(Protocol):
    async def get(self, user_id: int) -> dict[str, Any] | None: ...

    async def save(self, user_id: int, memory: AgentMemoryState) -> None: ...

    async def delete(self, user_id: int) -> bool: ...


def normalize_stored_messages(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    messages: list[dict[str, Any]] = []
    for item in value[-100:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        text = str(item.get("text") or "")
        if not text:
            continue
        message: dict[str, Any] = {
            "role": item["role"],
            "text": text[:4000],
        }
        if item.get("has_image"):
            message["has_image"] = True
        messages.append(message)
    return messages


class SupabaseAgentMemoryStore:
    """Persist one compact memory-and-goal row for each signed-in user."""

    async def get(self, user_id: int) -> dict[str, Any] | None:
        if not supabase_enabled():
            return None
        row = await supabase_select_one(
            "agent_memories",
            columns="user_id,summary,goals",
            filters={"user_id": int(user_id)},
        )
        if not row:
            return None
        return {
            "summary": str(row.get("summary") or "")[:1200],
            "goals": row.get("goals") if isinstance(row.get("goals"), list) else [],
        }

    async def save(self, user_id: int, memory: AgentMemoryState) -> None:
        if not supabase_enabled():
            return
        await supabase_request(
            "POST",
            "agent_memories",
            params={"on_conflict": "user_id"},
            json={
                "user_id": int(user_id),
                "summary": memory.summary,
                "goals": [goal.model_dump() for goal in memory.goals],
            },
            prefer="resolution=merge-duplicates,return=minimal",
        )

    async def delete(self, user_id: int) -> bool:
        if not supabase_enabled():
            return False
        rows = await supabase_delete(
            "agent_memories",
            filters={"user_id": int(user_id)},
            returning=True,
        )
        return bool(rows)


class SupabaseAgentConversationStore:
    """Persist user-owned ReAgent conversations through the server role."""

    _COLUMNS = (
        "id,user_id,language,title,messages,session_items,pending_state,"
        "pending_action,pending_request_id,consent_granted"
    )

    async def save(self, conversation: dict[str, Any]) -> None:
        if not supabase_enabled():
            return
        row = {
            "id": conversation["conversation_id"],
            "user_id": int(conversation["user_id"]),
            "language": normalize_agent_language(conversation.get("language", "en")),
            "title": str(conversation.get("title") or "New chat")[:80],
            "messages": normalize_stored_messages(conversation.get("messages")),
            "session_items": list(conversation.get("session_items") or [])[-200:],
            "pending_state": conversation.get("pending_state"),
            "pending_action": str(conversation.get("pending_action") or "")[:64],
            "pending_request_id": str(conversation.get("pending_request_id") or "")[:256],
            "consent_granted": bool(conversation.get("consent_granted")),
        }
        await supabase_request(
            "POST",
            "agent_conversations",
            params={"on_conflict": "id"},
            json=row,
            prefer="resolution=merge-duplicates,return=minimal",
        )

    async def list(self, user_id: int) -> list[dict[str, Any]]:
        if not supabase_enabled():
            return []
        rows = await supabase_select(
            "agent_conversations",
            columns=self._COLUMNS,
            filters={"user_id": int(user_id)},
            order="touched_at.desc",
            limit=50,
        )
        return [self._from_row(row) for row in rows or []]

    async def get(
        self,
        user_id: int,
        conversation_id: str,
    ) -> dict[str, Any] | None:
        if not supabase_enabled():
            return None
        row = await supabase_select_one(
            "agent_conversations",
            columns=self._COLUMNS,
            filters={
                "id": str(conversation_id),
                "user_id": int(user_id),
            },
        )
        return self._from_row(row) if row else None

    async def delete(self, user_id: int, conversation_id: str) -> bool:
        if not supabase_enabled():
            return False
        rows = await supabase_delete(
            "agent_conversations",
            filters={
                "id": str(conversation_id),
                "user_id": int(user_id),
            },
            returning=True,
        )
        return bool(rows)

    @staticmethod
    def _from_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "conversation_id": str(row.get("id") or ""),
            "user_id": int(row.get("user_id")),
            "language": normalize_agent_language(row.get("language", "en")),
            "title": str(row.get("title") or "New chat")[:80],
            "messages": normalize_stored_messages(row.get("messages")),
            "session_items": list(row.get("session_items") or [])[-200:],
            "pending_state": row.get("pending_state")
            if isinstance(row.get("pending_state"), dict)
            else None,
            "pending_action": str(row.get("pending_action") or "")[:64],
            "pending_request_id": str(row.get("pending_request_id") or "")[:256],
            "consent_granted": bool(row.get("consent_granted")),
        }
