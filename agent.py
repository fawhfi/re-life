"""OpenAI Agents SDK runtime and user-scoped ReAgent sessions."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import json
import math
import secrets
import time
from typing import Any, Protocol

from agents import (
    Agent,
    ModelSettings,
    OpenAIProvider,
    RunContextWrapper,
    Runner,
    RunState,
    SQLiteSession,
    function_tool,
    set_default_openai_key,
    set_tracing_disabled,
)

from config import (
    AGENT_API_KEY,
    AGENT_API_MODE,
    AGENT_BASE_URL,
    AGENT_MODEL,
    AGENT_SESSION_TTL_SECONDS,
)


if AGENT_BASE_URL:
    # Custom-provider runs must not export a second copy of user data to OpenAI tracing.
    set_tracing_disabled(True)
elif AGENT_API_KEY:
    set_default_openai_key(AGENT_API_KEY)


def _build_agent_model(
    *,
    model_name: str,
    api_key: str,
    base_url: str,
    api_mode: str,
) -> Any:
    """Build an Agents SDK model while preserving native OpenAI defaults."""
    if api_mode not in {"auto", "responses", "chat_completions"}:
        raise ValueError(f"Unsupported agent API mode: {api_mode}")
    if not base_url and (api_mode != "chat_completions" or not api_key):
        return model_name

    provider = OpenAIProvider(
        api_key=api_key or "not-required",
        base_url=base_url or None,
        use_responses=api_mode == "responses",
    )
    return provider.get_model(model_name)


def _build_agent_model_settings(*, custom_endpoint: bool) -> ModelSettings:
    """Use only portable request settings with OpenAI-compatible endpoints."""
    if custom_endpoint:
        return ModelSettings(parallel_tool_calls=False)
    return ModelSettings(
        parallel_tool_calls=False,
        store=False,
        verbosity="low",
    )


class AgentConversationNotFound(LookupError):
    pass


class AgentToolNotAllowed(PermissionError):
    pass


class AgentInputError(ValueError):
    pass


class AgentConsentRequired(PermissionError):
    pass


class AgentNotConfigured(RuntimeError):
    pass


class AgentProtocolError(RuntimeError):
    pass


RecyclingLookup = Callable[..., Awaitable[dict[str, Any]]]
WeatherLookup = Callable[..., Awaitable[dict[str, Any]]]
RecordsLookup = Callable[..., Awaitable[list[dict[str, Any]]]]
GuideLookup = Callable[[str], dict[str, Any]]


@dataclass(slots=True)
class AgentRunContext:
    user_id: int
    language: str
    recycling_lookup: RecyclingLookup
    weather_lookup: WeatherLookup
    records_lookup: RecordsLookup
    guide_lookup: GuideLookup
    location: tuple[float, float] | None = None
    last_points: list[dict[str, Any]] = field(default_factory=list)
    tool_trace: list[dict[str, str]] = field(default_factory=list)


async def get_user_location_impl(ctx: RunContextWrapper[AgentRunContext]) -> str:
    """Confirm whether the user granted browser location for this run."""
    available = ctx.context.location is not None
    ctx.context.tool_trace.append({
        "name": "get_user_location",
        "status": "completed" if available else "unavailable",
    })
    return json.dumps({"available": available})


async def find_recycling_points_impl(
    ctx: RunContextWrapper[AgentRunContext],
    material: str = "",
    limit: int = 5,
    distance_km: int = 3,
) -> str:
    """Find official Hong Kong recycling points near the approved browser location."""
    context = ctx.context
    context.tool_trace.append({"name": "find_recycling_points", "status": "started"})
    if context.location is None:
        context.tool_trace[-1]["status"] = "location_required"
        return json.dumps({"points": [], "error": "Location permission is required."})

    latitude, longitude = context.location
    if not (22.0 <= latitude <= 22.7 and 113.8 <= longitude <= 114.5):
        context.tool_trace[-1]["status"] = "unsupported_location"
        return json.dumps({
            "points": [],
            "error": "The nearby recycling tool currently supports Hong Kong only.",
        })

    safe_material = str(material or "").strip()[:64] or None
    safe_limit = _bounded_int(limit, default=5, minimum=1, maximum=5)
    safe_distance = _bounded_int(distance_km, default=3, minimum=1, maximum=10)
    payload = await context.recycling_lookup(
        latitude,
        longitude,
        material=safe_material,
        limit=safe_limit,
        distance_km=safe_distance,
    )
    raw_points = payload.get("points", []) if isinstance(payload, dict) else []
    context.last_points = [
        _public_recycling_point(point)
        for point in raw_points[:safe_limit]
        if isinstance(point, dict)
    ]
    context.tool_trace[-1]["status"] = "completed"
    return json.dumps({
        "points": context.last_points,
        "source": str(payload.get("source") or "") if isinstance(payload, dict) else "",
        "source_url": str(payload.get("source_url") or "") if isinstance(payload, dict) else "",
    }, ensure_ascii=False)


async def get_current_weather_impl(ctx: RunContextWrapper[AgentRunContext]) -> str:
    """Get current Hong Kong weather for the approved browser location."""
    context = ctx.context
    context.tool_trace.append({"name": "get_current_weather", "status": "started"})
    if context.location is None:
        context.tool_trace[-1]["status"] = "location_required"
        return json.dumps({"error": "Location permission is required."})
    latitude, longitude = context.location
    payload = await context.weather_lookup(latitude=latitude, longitude=longitude)
    context.tool_trace[-1]["status"] = "completed"
    return json.dumps({
        key: payload.get(key)
        for key in (
            "temperature",
            "summary",
            "location",
            "humidity",
            "updated_at",
            "warning",
        )
        if isinstance(payload, dict) and payload.get(key) is not None
    }, ensure_ascii=False)


async def get_recycling_guidance_impl(
    ctx: RunContextWrapper[AgentRunContext],
    material: str,
) -> str:
    """Get Re-Life's local sorting and disposal guidance for a material."""
    safe_material = str(material or "").strip().lower()[:64]
    ctx.context.tool_trace.append({"name": "get_recycling_guidance", "status": "completed"})
    payload = ctx.context.guide_lookup(safe_material)
    return json.dumps(payload if isinstance(payload, dict) else {}, ensure_ascii=False)


async def get_recent_recycling_records_impl(
    ctx: RunContextWrapper[AgentRunContext],
    limit: int = 5,
) -> str:
    """Get a small read-only summary of the signed-in user's recent scan records."""
    safe_limit = _bounded_int(limit, default=5, minimum=1, maximum=10)
    records = await ctx.context.records_lookup(
        user_id=ctx.context.user_id,
        limit=safe_limit,
    )
    safe_records = [
        _public_record(record)
        for record in records[:safe_limit]
        if isinstance(record, dict)
    ]
    ctx.context.tool_trace.append({
        "name": "get_recent_recycling_records",
        "status": "completed",
    })
    return json.dumps({"records": safe_records}, ensure_ascii=False)


get_user_location = function_tool(
    get_user_location_impl,
    name_override="get_user_location",
    description_override=(
        "Request the signed-in user's browser location. Use this before any tool that "
        "depends on the user's current location. This pauses for explicit user approval."
    ),
    needs_approval=True,
)
find_recycling_points = function_tool(
    find_recycling_points_impl,
    name_override="find_recycling_points",
)
get_current_weather = function_tool(
    get_current_weather_impl,
    name_override="get_current_weather",
)
get_recycling_guidance = function_tool(
    get_recycling_guidance_impl,
    name_override="get_recycling_guidance",
)
get_recent_recycling_records = function_tool(
    get_recent_recycling_records_impl,
    name_override="get_recent_recycling_records",
    needs_approval=True,
)


RELIFE_AGENT = Agent[AgentRunContext](
    name="ReAgent",
    instructions=(
        "You are ReAgent, a practical Hong Kong recycling assistant. "
        "Resolve the user's recycling question with the smallest useful set of read-only tools. "
        "Call get_user_location before location-dependent tools unless location was already "
        "approved in this conversation. Never state or expose coordinates. Use "
        "find_recycling_points for nearby collection requests, get_current_weather for trip "
        "conditions, get_recycling_guidance for sorting questions, and "
        "get_recent_recycling_records only for the signed-in user's own history. "
        "If a tool is unavailable or returns no evidence, say so instead of guessing. "
        "Reply in the language used by the user and keep the answer focused."
    ),
    model=_build_agent_model(
        model_name=AGENT_MODEL,
        api_key=AGENT_API_KEY,
        base_url=AGENT_BASE_URL,
        api_mode=AGENT_API_MODE,
    ),
    model_settings=_build_agent_model_settings(custom_endpoint=bool(AGENT_BASE_URL)),
    tools=[
        get_user_location,
        find_recycling_points,
        get_current_weather,
        get_recycling_guidance,
        get_recent_recycling_records,
    ],
)


@dataclass(slots=True)
class AgentRuntimeOutcome:
    status: str
    message: str
    request_id: str = ""
    action_type: str = ""
    pending_state: dict[str, Any] | None = None


class AgentRuntime(Protocol):
    async def start(
        self,
        message: str,
        *,
        context: AgentRunContext,
        session: Any,
    ) -> AgentRuntimeOutcome: ...

    async def resume(
        self,
        state: dict[str, Any],
        *,
        context: AgentRunContext,
        session: Any,
        approved: bool,
    ) -> AgentRuntimeOutcome: ...


class OpenAIAgentsRuntime:
    """Thin adapter around the official OpenAI Agents SDK runner."""

    def __init__(self, agent: Agent[AgentRunContext] = RELIFE_AGENT):
        self.agent = agent

    async def start(
        self,
        message: str,
        *,
        context: AgentRunContext,
        session: Any,
    ) -> AgentRuntimeOutcome:
        self._ensure_configured()
        result = await Runner.run(
            self.agent,
            message,
            context=context,
            session=session,
            max_turns=8,
        )
        return self._outcome(result)

    async def resume(
        self,
        state: dict[str, Any],
        *,
        context: AgentRunContext,
        session: Any,
        approved: bool,
    ) -> AgentRuntimeOutcome:
        self._ensure_configured()
        run_state = await RunState.from_json(
            self.agent,
            state,
            context_override=context,
            strict_context=True,
        )
        interruptions = run_state.get_interruptions()
        if not interruptions:
            raise AgentProtocolError("The saved agent run has no pending location request")
        for interruption in interruptions:
            if _interruption_name(interruption) not in {
                "get_user_location",
                "get_recent_recycling_records",
            }:
                raise AgentToolNotAllowed("Agent requested approval for a disallowed tool")
            if approved:
                run_state.approve(interruption)
            else:
                rejection = (
                    "The user did not share their location."
                    if _interruption_name(interruption) == "get_user_location"
                    else "The user did not allow access to recent recycling records."
                )
                run_state.reject(
                    interruption,
                    rejection_message=rejection,
                )
        result = await Runner.run(self.agent, run_state, session=session)
        return self._outcome(result)

    def _ensure_configured(self) -> None:
        if isinstance(self.agent.model, str) and not AGENT_API_KEY:
            raise AgentNotConfigured(
                "AGENT_API_KEY, OPENAI_API_KEY, or OPENAI_API is required"
            )

    @staticmethod
    def _outcome(result: Any) -> AgentRuntimeOutcome:
        interruptions = list(getattr(result, "interruptions", []) or [])
        if interruptions:
            if len(interruptions) != 1:
                raise AgentProtocolError("Only one user approval may be pending at a time")
            interruption = interruptions[0]
            tool_name = _interruption_name(interruption)
            action = {
                "get_user_location": (
                    "get_user_location",
                    "I need your location permission to continue.",
                ),
                "get_recent_recycling_records": (
                    "read_user_records",
                    "Allow access to your recent recycling records?",
                ),
            }.get(tool_name)
            if not action:
                raise AgentToolNotAllowed("Agent attempted to pause for a disallowed tool")
            state = result.to_state().to_json(
                context_serializer=lambda context: {
                    "user_id": context.user_id,
                    "language": context.language,
                },
                strict_context=True,
            )
            return AgentRuntimeOutcome(
                status="requires_action",
                message=action[1],
                request_id=_interruption_call_id(interruption),
                action_type=action[0],
                pending_state=state,
            )
        message = str(getattr(result, "final_output", "") or "").strip()
        if not message:
            raise AgentProtocolError("Agent returned an empty response")
        return AgentRuntimeOutcome(status="completed", message=message)


@dataclass(slots=True)
class _AgentSandbox:
    conversation_id: str
    user_id: int
    language: str
    created_at: float
    touched_at: float
    session: Any
    pending_state: dict[str, Any] | None = None
    pending_action: str = ""
    pending_request_id: str = ""
    consent_granted: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class AgentSandboxService:
    """Lazily creates ephemeral, user-owned SDK sessions and paused run state."""

    def __init__(
        self,
        *,
        recycling_lookup: RecyclingLookup,
        weather_lookup: WeatherLookup,
        records_lookup: RecordsLookup,
        guide_lookup: GuideLookup,
        runtime: AgentRuntime | None = None,
        session_factory: Callable[[str], Any] = SQLiteSession,
        ttl_seconds: int = AGENT_SESSION_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._runtime = runtime or OpenAIAgentsRuntime()
        self._recycling_lookup = recycling_lookup
        self._weather_lookup = weather_lookup
        self._records_lookup = records_lookup
        self._guide_lookup = guide_lookup
        self._session_factory = session_factory
        self._ttl_seconds = max(60, int(ttl_seconds))
        self._clock = clock
        self._sandboxes: dict[str, _AgentSandbox] = {}
        self._store_lock = asyncio.Lock()

    async def respond(
        self,
        *,
        user_id: int,
        message: str | None = None,
        conversation_id: str | None = None,
        location: dict[str, Any] | None = None,
        location_error: str | None = None,
        approval: dict[str, Any] | None = None,
        request_id: str | None = None,
        language: str = "en",
        data_consent: bool = False,
    ) -> dict[str, Any]:
        has_message = message is not None
        has_location_response = location is not None or location_error is not None
        has_approval = approval is not None
        if sum((has_message, has_location_response, has_approval)) != 1:
            raise AgentInputError("Send one message, location response, or approval response")
        if not conversation_id and has_message and not data_consent:
            raise AgentConsentRequired("Explicit agent data consent is required")

        sandbox = await self._get_or_create(
            user_id=int(user_id),
            conversation_id=conversation_id,
            language=language,
            allow_create=has_message,
            consent_granted=bool(data_consent),
        )
        async with sandbox.lock:
            sandbox.touched_at = self._clock()
            context = AgentRunContext(
                user_id=sandbox.user_id,
                language=sandbox.language,
                recycling_lookup=self._recycling_lookup,
                weather_lookup=self._weather_lookup,
                records_lookup=self._records_lookup,
                guide_lookup=self._guide_lookup,
            )

            if has_message:
                cleaned = str(message).strip()
                if not cleaned or len(cleaned) > 2000:
                    raise AgentInputError("Agent messages must contain 1 to 2000 characters")
                if sandbox.pending_state:
                    raise AgentInputError("Resolve the pending location request first")
                outcome = await self._runtime.start(
                    cleaned,
                    context=context,
                    session=sandbox.session,
                )
            elif has_location_response:
                if not sandbox.pending_state:
                    raise AgentInputError("There is no pending location request")
                if sandbox.pending_action != "get_user_location":
                    raise AgentInputError("The pending approval is not a location request")
                if str(request_id or "") != sandbox.pending_request_id:
                    raise AgentInputError("Location request ID does not match the pending action")
                approved = location is not None
                if location is not None:
                    context.location = (
                        _finite_coordinate(location.get("latitude"), -90, 90, "latitude"),
                        _finite_coordinate(location.get("longitude"), -180, 180, "longitude"),
                    )
                outcome = await self._runtime.resume(
                    sandbox.pending_state,
                    context=context,
                    session=sandbox.session,
                    approved=approved,
                )
            else:
                if not sandbox.pending_state:
                    raise AgentInputError("There is no pending data access approval")
                approval_type = str(approval.get("type") or "")
                if approval_type != sandbox.pending_action:
                    raise AgentInputError("Approval type does not match the pending agent action")
                if str(approval.get("request_id") or "") != sandbox.pending_request_id:
                    raise AgentInputError("Approval request ID does not match the pending action")
                outcome = await self._runtime.resume(
                    sandbox.pending_state,
                    context=context,
                    session=sandbox.session,
                    approved=bool(approval.get("approved")),
                )

            sandbox.pending_state = outcome.pending_state
            sandbox.pending_action = outcome.action_type if outcome.pending_state else ""
            sandbox.pending_request_id = outcome.request_id if outcome.pending_state else ""
            response = {
                "conversation_id": sandbox.conversation_id,
                "status": outcome.status,
                "message": outcome.message,
                "points": context.last_points,
                "tool_trace": context.tool_trace,
            }
            if outcome.status == "requires_action":
                response["action"] = {
                    "type": outcome.action_type,
                    "request_id": outcome.request_id,
                }
            return response

    async def destroy(self, user_id: int, conversation_id: str) -> bool:
        async with self._store_lock:
            sandbox = self._sandboxes.get(str(conversation_id))
            if not sandbox or sandbox.user_id != int(user_id):
                return False
            del self._sandboxes[sandbox.conversation_id]
        clear = getattr(sandbox.session, "clear_session", None)
        if clear:
            await clear()
        return True

    async def _get_or_create(
        self,
        *,
        user_id: int,
        conversation_id: str | None,
        language: str,
        allow_create: bool,
        consent_granted: bool,
    ) -> _AgentSandbox:
        now = self._clock()
        async with self._store_lock:
            self._purge_expired_locked(now)
            if conversation_id:
                sandbox = self._sandboxes.get(str(conversation_id))
                if not sandbox or sandbox.user_id != user_id:
                    raise AgentConversationNotFound("Agent conversation not found")
                sandbox.language = _normalize_language(language)
                return sandbox
            if not allow_create:
                raise AgentConversationNotFound("Agent conversation not found")

            new_id = secrets.token_urlsafe(24)
            sandbox = _AgentSandbox(
                conversation_id=new_id,
                user_id=user_id,
                language=_normalize_language(language),
                created_at=now,
                touched_at=now,
                session=self._session_factory(new_id),
                consent_granted=consent_granted,
            )
            self._sandboxes[new_id] = sandbox
            return sandbox

    def _purge_expired_locked(self, now: float) -> None:
        expired = [
            conversation_id
            for conversation_id, sandbox in self._sandboxes.items()
            if now - sandbox.touched_at > self._ttl_seconds
        ]
        for conversation_id in expired:
            del self._sandboxes[conversation_id]


def _public_recycling_point(point: dict[str, Any]) -> dict[str, Any]:
    return {
        key: point.get(key)
        for key in (
            "name",
            "distance_m",
            "materials",
            "open_hours",
            "accessibility",
            "maps_url",
            "detail_url",
        )
        if point.get(key) not in (None, "", [])
    }


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: record.get(key)
        for key in (
            "id",
            "name",
            "brand",
            "category",
            "material",
            "mode",
            "eco_rate",
            "recycle_rate",
            "created_at",
            "date",
        )
        if record.get(key) not in (None, "")
    }


def _interruption_name(interruption: Any) -> str:
    return str(
        getattr(interruption, "name", None)
        or getattr(interruption, "tool_name", None)
        or ""
    )


def _interruption_call_id(interruption: Any) -> str:
    raw = getattr(interruption, "raw_item", None)
    if isinstance(raw, dict):
        return str(raw.get("call_id") or raw.get("id") or "")
    return str(getattr(raw, "call_id", None) or getattr(raw, "id", None) or "")


def _normalize_language(language: str) -> str:
    value = str(language or "en").strip().lower()
    return value if value in {"zh_simplified", "zh_traditional"} else "en"


def _finite_coordinate(value: Any, minimum: float, maximum: float, label: str) -> float:
    try:
        coordinate = float(value)
    except (TypeError, ValueError) as exc:
        raise AgentInputError(f"Invalid {label}") from exc
    if not math.isfinite(coordinate) or not minimum <= coordinate <= maximum:
        raise AgentInputError(f"Invalid {label}")
    return coordinate


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))
