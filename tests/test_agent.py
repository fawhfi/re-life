import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from config import SESSION_COOKIE_NAME
from sessions import SessionContext


class FakeAgentSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.cleared = False

    async def clear_session(self):
        self.cleared = True


class ScriptedAgentRuntime:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def start(self, message, *, context, session):
        self.calls.append(("start", message, context, session))
        return self.outcomes.pop(0)

    async def resume(self, state, *, context, session, approved):
        self.calls.append(("resume", state, context, session, approved))
        return self.outcomes.pop(0)


class AgentSDKContractTests(unittest.TestCase):
    def test_official_openai_agents_sdk_is_pinned_to_current_minor(self):
        requirements = Path("requirements.txt").read_text(encoding="utf-8")
        template_env = Path("template.env").read_text(encoding="utf-8")

        self.assertIn("openai-agents>=0.18.3,<0.19", requirements)
        self.assertIn("AGENT_MODEL=gpt-5.6", template_env)
        self.assertIn("AGENT_BASE_URL=", template_env)
        self.assertIn("AGENT_API_KEY=", template_env)
        self.assertIn("AGENT_API_MODE=auto", template_env)
        self.assertIn("AGENT_SESSION_TTL_SECONDS=1800", template_env)

    def test_agent_builds_models_for_openai_compatible_custom_endpoints(self):
        from agents import OpenAIChatCompletionsModel, OpenAIResponsesModel

        from agent import _build_agent_model

        chat_model = _build_agent_model(
            model_name="local-tool-model",
            api_key="custom-key",
            base_url="https://llm.example.com/v1",
            api_mode="auto",
        )
        responses_model = _build_agent_model(
            model_name="responses-tool-model",
            api_key="custom-key",
            base_url="https://responses.example.com/v1",
            api_mode="responses",
        )

        self.assertIsInstance(chat_model, OpenAIChatCompletionsModel)
        self.assertEqual(chat_model.model, "local-tool-model")
        self.assertEqual(str(chat_model._client.base_url), "https://llm.example.com/v1/")
        self.assertEqual(chat_model._client.api_key, "custom-key")
        self.assertIsInstance(responses_model, OpenAIResponsesModel)
        self.assertEqual(responses_model.model, "responses-tool-model")

    def test_agent_keeps_native_openai_model_resolution_without_custom_url(self):
        from agent import _build_agent_model

        self.assertEqual(
            _build_agent_model(
                model_name="gpt-5.6",
                api_key="openai-key",
                base_url="",
                api_mode="auto",
            ),
            "gpt-5.6",
        )

    def test_custom_agent_endpoint_never_reuses_the_openai_api_key(self):
        import config

        try:
            with patch.dict(os.environ, {
                "AGENT_BASE_URL": "https://third-party.example.com/v1",
                "OPENAI_API_KEY": "must-not-leak",
            }, clear=True):
                reloaded = importlib.reload(config)

                self.assertEqual(reloaded.AGENT_BASE_URL, "https://third-party.example.com/v1")
                self.assertEqual(reloaded.AGENT_API_KEY, "")
                self.assertEqual(reloaded.AGENT_API_MODE, "auto")
        finally:
            importlib.reload(config)

    def test_custom_endpoint_uses_portable_model_settings(self):
        from agent import _build_agent_model_settings

        settings = _build_agent_model_settings(custom_endpoint=True)

        self.assertFalse(settings.parallel_tool_calls)
        self.assertIsNone(settings.store)
        self.assertIsNone(settings.verbosity)

    def test_agent_exposes_only_the_initial_read_only_tool_set(self):
        from agent import RELIFE_AGENT

        self.assertEqual(RELIFE_AGENT.name, "ReAgent")
        tools = {tool.name: tool for tool in RELIFE_AGENT.tools}
        self.assertEqual(
            set(tools),
            {
                "get_user_location",
                "find_recycling_points",
                "get_current_weather",
                "get_recycling_guidance",
                "get_recent_recycling_records",
            },
        )
        self.assertTrue(tools["get_user_location"].needs_approval)
        self.assertTrue(tools["get_recent_recycling_records"].needs_approval)
        self.assertFalse(any(name in tools for name in ("shell", "run_shell", "apply_patch")))


class AgentSDKRunStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_sdk_pauses_serializes_and_resumes_location_tool(self):
        from collections.abc import AsyncIterator

        from agents import Agent, ModelSettings, SQLiteSession
        from agents.items import ModelResponse
        from agents.models.interface import Model
        from agents.usage import Usage
        from openai.types.responses import (
            ResponseFunctionToolCall,
            ResponseOutputMessage,
            ResponseOutputText,
        )

        from agent import AgentRunContext, OpenAIAgentsRuntime, RELIFE_AGENT

        class FakeSDKModel(Model):
            def __init__(self):
                self.outputs = [
                    [ResponseFunctionToolCall(
                        id="tool-1",
                        call_id="location-1",
                        name="get_user_location",
                        arguments="{}",
                        status="completed",
                        type="function_call",
                    )],
                    [ResponseOutputMessage(
                        id="message-1",
                        role="assistant",
                        status="completed",
                        type="message",
                        content=[ResponseOutputText(
                            annotations=[],
                            logprobs=[],
                            text="Location is available.",
                            type="output_text",
                        )],
                    )],
                ]

            async def get_response(self, *args, **kwargs):
                return ModelResponse(
                    output=self.outputs.pop(0),
                    usage=Usage(),
                    response_id="response-1",
                )

            async def stream_response(self, *args, **kwargs) -> AsyncIterator:
                if False:
                    yield None
                raise AssertionError("Streaming is not used in this test")

        sdk_agent = Agent[AgentRunContext](
            name="Re-Life Agent test",
            instructions=RELIFE_AGENT.instructions,
            model=FakeSDKModel(),
            model_settings=ModelSettings(parallel_tool_calls=False, store=False),
            tools=RELIFE_AGENT.tools,
        )
        runtime = OpenAIAgentsRuntime(sdk_agent)
        session = SQLiteSession("sdk-run-state-test")
        base_context = dict(
            user_id=7,
            language="en",
            recycling_lookup=AsyncMock(),
            weather_lookup=AsyncMock(),
            records_lookup=AsyncMock(),
            guide_lookup=lambda material: {},
        )

        first = await runtime.start(
            "Use my location",
            context=AgentRunContext(**base_context),
            session=session,
        )
        second = await runtime.resume(
            first.pending_state,
            context=AgentRunContext(
                **base_context,
                location=(22.280255, 114.165827),
            ),
            session=session,
            approved=True,
        )

        self.assertEqual(first.status, "requires_action")
        self.assertEqual(first.action_type, "get_user_location")
        self.assertEqual(first.request_id, "location-1")
        self.assertIn("$schemaVersion", first.pending_state)
        self.assertEqual(second.status, "completed")
        self.assertEqual(second.message, "Location is available.")


class AgentToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_tools_use_server_context_without_exposing_coordinates(self):
        from agent import (
            AgentRunContext,
            find_recycling_points_impl,
            get_current_weather_impl,
            get_recent_recycling_records_impl,
            get_recycling_guidance_impl,
            get_user_location_impl,
        )

        recycling_lookup = AsyncMock(return_value={
            "points": [{"name": "Central", "distance_m": 180, "materials": ["Plastic"]}],
            "source": "wastereduction.gov.hk",
            "source_url": "https://www.wastereduction.gov.hk/zh-hk/recycling-map?x=1",
        })
        weather_lookup = AsyncMock(return_value={
            "temperature": 29,
            "summary": "Cloudy",
            "location": "Hong Kong",
        })
        records_lookup = AsyncMock(return_value=[{
            "id": "record-1",
            "name": "Water bottle",
            "material": "plastic",
            "created_at": "2026-07-19T08:00:00Z",
        }])
        guide_lookup = lambda material: {
            "type": "Plastic",
            "method": "Rinse clean",
            "location": "GREEN@COMMUNITY",
        }
        context = AgentRunContext(
            user_id=7,
            language="en",
            location=(22.280255, 114.165827),
            recycling_lookup=recycling_lookup,
            weather_lookup=weather_lookup,
            records_lookup=records_lookup,
            guide_lookup=guide_lookup,
        )
        wrapper = SimpleNamespace(context=context)

        location_result = json.loads(await get_user_location_impl(wrapper))
        points_result = json.loads(await find_recycling_points_impl(
            wrapper,
            material="plastic",
            limit=3,
            distance_km=3,
        ))
        weather_result = json.loads(await get_current_weather_impl(wrapper))
        guide_result = json.loads(await get_recycling_guidance_impl(wrapper, material="plastic"))
        records_result = json.loads(await get_recent_recycling_records_impl(wrapper, limit=3))

        self.assertEqual(location_result, {"available": True})
        self.assertEqual(points_result["points"][0]["name"], "Central")
        self.assertEqual(weather_result["temperature"], 29)
        self.assertEqual(guide_result["method"], "Rinse clean")
        self.assertEqual(records_result["records"][0]["name"], "Water bottle")
        self.assertEqual(context.last_points[0]["name"], "Central")
        self.assertEqual(
            [event["name"] for event in context.tool_trace],
            [
                "get_user_location",
                "find_recycling_points",
                "get_current_weather",
                "get_recycling_guidance",
                "get_recent_recycling_records",
            ],
        )

        model_visible_outputs = json.dumps(
            [location_result, points_result, weather_result, guide_result, records_result],
            ensure_ascii=False,
        )
        self.assertNotIn("22.280255", model_visible_outputs)
        self.assertNotIn("114.165827", model_visible_outputs)
        recycling_lookup.assert_awaited_once_with(
            22.280255,
            114.165827,
            material="plastic",
            limit=3,
            distance_km=3,
        )
        weather_lookup.assert_awaited_once_with(latitude=22.280255, longitude=114.165827)
        records_lookup.assert_awaited_once_with(user_id=7, limit=3)


class AgentSandboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_pauses_for_browser_location_then_resumes_same_sdk_run(self):
        from agent import AgentRuntimeOutcome, AgentSandboxService

        runtime = ScriptedAgentRuntime(
            AgentRuntimeOutcome(
                status="requires_action",
                message="I need your location permission to continue.",
                request_id="location-1",
                action_type="get_user_location",
                pending_state={"sdk": "paused"},
            ),
            AgentRuntimeOutcome(
                status="completed",
                message="I found the nearest plastic recycling points.",
            ),
        )
        sessions = []

        def session_factory(session_id):
            session = FakeAgentSession(session_id)
            sessions.append(session)
            return session

        service = AgentSandboxService(
            runtime=runtime,
            recycling_lookup=AsyncMock(),
            weather_lookup=AsyncMock(),
            records_lookup=AsyncMock(),
            guide_lookup=lambda material: {},
            session_factory=session_factory,
            clock=lambda: 100.0,
        )

        first = await service.respond(
            user_id=7,
            message="Where can I recycle plastic near me?",
            language="en",
            data_consent=True,
        )
        second = await service.respond(
            user_id=7,
            conversation_id=first["conversation_id"],
            location={"latitude": 22.280255, "longitude": 114.165827, "accuracy": 25},
            request_id="location-1",
            language="en",
        )

        self.assertEqual(first["status"], "requires_action")
        self.assertEqual(first["action"], {
            "type": "get_user_location",
            "request_id": "location-1",
        })
        self.assertEqual(second["status"], "completed")
        self.assertEqual(second["message"], "I found the nearest plastic recycling points.")
        self.assertEqual([call[0] for call in runtime.calls], ["start", "resume"])
        self.assertEqual(runtime.calls[1][1], {"sdk": "paused"})
        self.assertEqual(runtime.calls[1][2].location, (22.280255, 114.165827))
        self.assertIs(runtime.calls[0][3], runtime.calls[1][3])
        self.assertEqual(len(sessions), 1)

    async def test_recent_records_tool_requires_a_separate_resumable_approval(self):
        from agent import AgentRuntimeOutcome, AgentSandboxService

        runtime = ScriptedAgentRuntime(
            AgentRuntimeOutcome(
                status="requires_action",
                message="Allow access to your recent recycling records?",
                request_id="records-1",
                action_type="read_user_records",
                pending_state={"sdk": "records-paused"},
            ),
            AgentRuntimeOutcome(status="completed", message="Your recent record was a bottle."),
        )
        service = AgentSandboxService(
            runtime=runtime,
            recycling_lookup=AsyncMock(),
            weather_lookup=AsyncMock(),
            records_lookup=AsyncMock(),
            guide_lookup=lambda material: {},
            session_factory=FakeAgentSession,
            clock=lambda: 100.0,
        )

        first = await service.respond(
            user_id=7,
            message="What did I recycle recently?",
            language="en",
            data_consent=True,
        )
        second = await service.respond(
            user_id=7,
            conversation_id=first["conversation_id"],
            approval={
                "type": "read_user_records",
                "request_id": "records-1",
                "approved": True,
            },
            language="en",
        )

        self.assertEqual(first["action"]["type"], "read_user_records")
        self.assertEqual(first["action"]["request_id"], "records-1")
        self.assertEqual(second["status"], "completed")
        self.assertTrue(runtime.calls[1][4])

    async def test_conversations_are_owned_by_one_authenticated_user(self):
        from agent import AgentConversationNotFound, AgentRuntimeOutcome, AgentSandboxService

        service = AgentSandboxService(
            runtime=ScriptedAgentRuntime(AgentRuntimeOutcome(status="completed", message="Hello")),
            recycling_lookup=AsyncMock(),
            weather_lookup=AsyncMock(),
            records_lookup=AsyncMock(),
            guide_lookup=lambda material: {},
            session_factory=FakeAgentSession,
            clock=lambda: 100.0,
        )
        response = await service.respond(
            user_id=7,
            message="Hello",
            language="en",
            data_consent=True,
        )

        with self.assertRaises(AgentConversationNotFound):
            await service.respond(
                user_id=8,
                conversation_id=response["conversation_id"],
                message="Read another user's chat",
                language="en",
            )

    async def test_destroy_clears_the_sdk_session(self):
        from agent import AgentRuntimeOutcome, AgentSandboxService

        session = FakeAgentSession("placeholder")
        service = AgentSandboxService(
            runtime=ScriptedAgentRuntime(AgentRuntimeOutcome(status="completed", message="Hello")),
            recycling_lookup=AsyncMock(),
            weather_lookup=AsyncMock(),
            records_lookup=AsyncMock(),
            guide_lookup=lambda material: {},
            session_factory=lambda _: session,
            clock=lambda: 100.0,
        )
        response = await service.respond(
            user_id=7,
            message="Hello",
            language="en",
            data_consent=True,
        )

        self.assertTrue(await service.destroy(7, response["conversation_id"]))
        self.assertTrue(session.cleared)

    async def test_new_agent_conversation_requires_explicit_data_consent(self):
        from agent import AgentConsentRequired, AgentRuntimeOutcome, AgentSandboxService

        service = AgentSandboxService(
            runtime=ScriptedAgentRuntime(AgentRuntimeOutcome(status="completed", message="Hello")),
            recycling_lookup=AsyncMock(),
            weather_lookup=AsyncMock(),
            records_lookup=AsyncMock(),
            guide_lookup=lambda material: {},
            session_factory=FakeAgentSession,
            clock=lambda: 100.0,
        )

        with self.assertRaises(AgentConsentRequired):
            await service.respond(
                user_id=7,
                message="Hello",
                language="en",
                data_consent=False,
            )


class AgentEndpointTests(unittest.TestCase):
    def setUp(self):
        from main import app

        self.client = TestClient(app)

    def _post_as_user(self, payload, user_id=7):
        context = SessionContext("agent-session", {"id": user_id}, False)
        with patch("sessions.resolve_session", new=AsyncMock(return_value=context)):
            self.client.cookies.set(SESSION_COOKIE_NAME, "agent-token")
            try:
                return self.client.post("/api/agent/messages", json=payload)
            finally:
                self.client.cookies.clear()

    def test_agent_messages_require_authentication(self):
        response = self.client.post("/api/agent/messages", json={"message": "Hello"})

        self.assertEqual(response.status_code, 401)

    def test_agent_message_endpoint_binds_request_to_authenticated_user(self):
        payload = {
            "conversation_id": "conversation-1",
            "status": "completed",
            "message": "Hello",
            "points": [],
            "tool_trace": [],
        }
        with patch("main.agent_service.respond", new=AsyncMock(return_value=payload)) as respond:
            response = self._post_as_user({
                "message": "How do I recycle glass?",
                "language": "en",
                "data_consent": True,
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        respond.assert_awaited_once_with(
            user_id=7,
            message="How do I recycle glass?",
            conversation_id=None,
            location=None,
            location_error=None,
            approval=None,
            request_id=None,
            language="en",
            data_consent=True,
        )

    def test_agent_message_body_rejects_client_selected_tools(self):
        response = self._post_as_user({
            "message": "Run this",
            "tool": "run_shell",
        })

        self.assertEqual(response.status_code, 422)

    def test_agent_location_resume_validates_coordinates(self):
        response = self._post_as_user({
            "conversation_id": "conversation-1",
            "location": {"latitude": 200, "longitude": 114.16},
        })

        self.assertEqual(response.status_code, 422)

    def test_agent_conversation_can_be_destroyed(self):
        with patch("main.agent_service.destroy", new=AsyncMock(return_value=True)) as destroy:
            context = SessionContext("agent-session", {"id": 7}, False)
            with patch("sessions.resolve_session", new=AsyncMock(return_value=context)):
                self.client.cookies.set(SESSION_COOKIE_NAME, "agent-token")
                try:
                    response = self.client.delete("/api/agent/conversations/conversation-1")
                finally:
                    self.client.cookies.clear()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        destroy.assert_awaited_once_with(7, "conversation-1")


class AgentFrontendContractTests(unittest.TestCase):
    def test_agent_tab_wires_chat_location_and_recycling_results(self):
        template = Path("templates/index.html").read_text(encoding="utf-8")
        app = Path("static/app.js").read_text(encoding="utf-8")
        agent_js = Path("static/js/app-agent.js").read_text(encoding="utf-8")
        i18n_js = Path("static/js/i18n.js").read_text(encoding="utf-8")
        style = Path("static/style.css").read_text(encoding="utf-8")
        en = json.loads(Path("static/i18n/en.json").read_text(encoding="utf-8"))
        zh_s = json.loads(Path("static/i18n/zh_simplified.json").read_text(encoding="utf-8"))
        zh_t = json.loads(Path("static/i18n/zh_traditional.json").read_text(encoding="utf-8"))

        self.assertIn('id="tab-agent"', template)
        self.assertIn('id="agent-title">ReAgent</h2>', template)
        self.assertIn('aria-label="Message ReAgent"', template)
        self.assertIn('id="agent-consent-title">Use ReAgent?</h2>', template)
        self.assertNotIn("Re-Life Agent", template)
        self.assertNotIn("Re-Life Agent", agent_js)
        self.assertIn('id="nav-agent"', template)
        self.assertIn('/static/js/app-agent.js', template)
        self.assertIn('/static/style.css?v=20260719-agent3', template)
        self.assertIn('/static/app.js?v=20260719-agent3', template)
        self.assertIn('/static/js/app-agent.js?v=20260719-agent3', template)
        self.assertLess(template.index('/static/js/app-weather.js'), template.index('/static/js/app-agent.js'))
        self.assertIn("'agent'", app[app.index("const TAB_ORDER"):])
        self.assertIn("/api/agent/messages", agent_js)
        self.assertIn("resolveWeatherCoordinates(true)", agent_js)
        self.assertIn("payload.action.type === 'get_user_location'", agent_js)
        self.assertIn("payload.action.type === 'read_user_records'", agent_js)
        self.assertIn("data_consent", agent_js)
        self.assertIn('id="agent-consent-dialog"', template)
        self.assertIn('id="agent-consent-allow"', template)
        self.assertNotIn("navigator.geolocation", agent_js)
        self.assertIn("I18N_CACHE_20260719_AGENT3", i18n_js)
        self.assertIn(".json?v=20260719-agent3", i18n_js)
        self.assertIn(".agent-shell", style)
        self.assertIn(".agent-message", style)

        for translations in (en, zh_s, zh_t):
            self.assertIn("agent", translations)
            self.assertEqual(translations["agent"]["title"], "ReAgent")
            self.assertIn("ReAgent", translations["agent"]["inputLabel"])
            self.assertIn("ReAgent", translations["agent"]["consentTitle"])
            self.assertNotIn("OpenAI", translations["agent"]["consentBody"])
            self.assertIn("send", translations["agent"])

        self.assertNotIn("processed by OpenAI", template)
        self.assertNotIn("processed by OpenAI", agent_js)


if __name__ == "__main__":
    unittest.main()
