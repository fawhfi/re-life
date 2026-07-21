"""Runtime adapter that preserves approvals across remote-to-local failover."""
from __future__ import annotations

from dataclasses import replace
import logging
from typing import Any


logger = logging.getLogger(__name__)


class FailoverAgentRuntime:
    """Keep one runtime interface while switching between two adapters."""

    def __init__(
        self,
        primary: Any,
        fallback: Any,
        *,
        non_failover_errors: tuple[type[BaseException], ...] = (),
    ):
        self._primary = primary
        self._fallback = fallback
        self._non_failover_errors = non_failover_errors

    async def start(self, message: str, *, context: Any, session: Any) -> Any:
        if bool(getattr(context, "force_local", False)):
            return await self._fallback.start(message, context=context, session=session)
        try:
            outcome = await self._primary.start(message, context=context, session=session)
            return self._wrap_primary_pending(outcome, message)
        except self._non_failover_errors:
            raise
        except Exception:
            logger.warning(
                "Remote ReAgent start failed; using the local runtime",
                exc_info=True,
            )
            return await self._fallback.start(message, context=context, session=session)

    async def resume(
        self,
        state: dict[str, Any],
        *,
        context: Any,
        session: Any,
        approved: bool,
    ) -> Any:
        if state.get("runtime") == "local":
            return await self._fallback.resume(
                state,
                context=context,
                session=session,
                approved=approved,
            )
        primary_state = state
        original_message = ""
        original_action = ""
        if state.get("runtime") == "primary" and isinstance(state.get("state"), dict):
            primary_state = state["state"]
            original_message = str(state.get("message") or "")[:2000]
            original_action = str(state.get("action_type") or "")[:64]
        try:
            outcome = await self._primary.resume(
                primary_state,
                context=context,
                session=session,
                approved=approved,
            )
            return self._wrap_primary_pending(outcome, original_message)
        except self._non_failover_errors:
            raise
        except Exception:
            logger.warning(
                "Remote ReAgent resume failed; using the local runtime",
                exc_info=True,
            )
            if original_message:
                planned = await self._fallback.start(
                    original_message,
                    context=context,
                    session=session,
                )
                if (
                    planned.status == "requires_action"
                    and planned.action_type == original_action
                    and planned.pending_state
                ):
                    return await self._fallback.resume(
                        planned.pending_state,
                        context=context,
                        session=session,
                        approved=approved,
                    )
                return planned
            return await self._fallback.resume(
                state,
                context=context,
                session=session,
                approved=approved,
            )

    @staticmethod
    def _wrap_primary_pending(outcome: Any, message: str) -> Any:
        if not outcome.pending_state:
            return outcome
        return replace(
            outcome,
            pending_state={
                "runtime": "primary",
                "version": 1,
                "state": outcome.pending_state,
                "message": str(message or "")[:2000],
                "action_type": outcome.action_type,
            },
        )
