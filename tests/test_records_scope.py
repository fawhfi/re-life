from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

import data


class RecordScopeTests(unittest.TestCase):
    def test_records_load_waits_for_account_init(self):
        source = Path("static/app.js").read_text(encoding="utf-8")
        records = Path("static/js/app-records.js").read_text(encoding="utf-8")

        self.assertNotIn(
            "Promise.all([initAccounts(), loadRecords()])",
            source,
        )
        self.assertIn("await initAccounts();", source)
        self.assertIn("await loadRecords();", source)
        self.assertNotIn("async function loadRecords({ force = false } = {})", source)
        self.assertNotIn("function renderRecords()", source)
        self.assertNotIn("function updateStats()", source)
        self.assertIn("function syncRecordsView()", records)
        self.assertIn("userName: record.userName || state.currentUser || null,", records)

    def test_nav_drag_commits_once_on_release(self):
        source = Path("static/app.js").read_text(encoding="utf-8")
        template = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("let suppressNavClickUntil = 0;", source)
        self.assertIn("const hadDrag = navbar.classList.contains('nav-is-dragging');", source)
        self.assertIn("function getTabName(btn)", source)
        self.assertIn("function getIndicatorBox(btn", source)
        self.assertIn("const baseLeft = 5;", source)
        self.assertNotIn("Math.min(295", source)
        self.assertIn("const targetTab = pendingTab || getBestTab(e.clientX);", source)
        self.assertIn('data-tab="home"', template)
        self.assertIn('data-tab="record"', template)
        self.assertIn("if (hadDrag) {", source)
        self.assertNotIn("if (m && m[1] && state.activeTab !== m[1]) navigateTo(m[1]);", source)

    def test_tab_switching_uses_gsap_animation(self):
        source = Path("static/app.js").read_text(encoding="utf-8")
        styles = Path("static/style.css").read_text(encoding="utf-8")

        self.assertIn("const TAB_ORDER = ['home', 'record', 'rewards', 'more'];", source)
        self.assertIn("function getTabDirection(nextName)", source)
        self.assertIn("gsap.timeline", source)
        self.assertIn("const lightTabAnimation = PERF.lowEnd", source)
        self.assertIn("function resetTabVisuals(tab)", source)
        self.assertIn("onInterrupt: () => cleanupTabTween", source)
        self.assertNotIn("autoAlpha", source)
        self.assertIn("tab-exiting", source)
        self.assertIn("runTabSideEffects(name);", source)
        self.assertIn(".tab-exiting", styles)
        self.assertIn(".nav-btn.is-active", styles)
        self.assertIn("transform: none;", styles)
        self.assertNotIn("@keyframes slideInTab", styles)

    def test_record_loading_uses_cache_for_same_user(self):
        source = Path("static/js/app-records.js").read_text(encoding="utf-8")

        self.assertIn("async function loadRecords({ force = false } = {})", source)
        self.assertIn("if (!force && !state.recordsDirty && state.recordsLoadedFor === cacheKey)", source)
        self.assertIn("if (state.recordsLoadPromise && state.recordsLoadPromiseToken === state.recordsLoadToken)", source)
        self.assertIn("syncRecordsView();", source)
        self.assertIn("upsertRecordCache(record)", source)
        self.assertIn("removeRecordCache(recordId)", source)

    def test_get_items_refuses_unauthenticated_reads(self):
        source = Path("static/supabase.js").read_text(encoding="utf-8")

        self.assertIn("function fallbackUserId()", source)
        self.assertIn("function fallbackUserName()", source)
        self.assertIn("if (!userId && !displayName && !userKey) return [];", source)
        self.assertIn("user_id: userId || fallbackUserId() || \"\"", source)
        self.assertIn("display_name: displayName || fallbackUserName() || \"\"", source)
        self.assertIn("user_key: userKey || \"\"", source)
        self.assertIn("async getItems(userId = null, displayName = null, userKey = null)", source)


class RecordInsertTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_item_omits_fields_missing_from_scan_records_schema(self):
        owner = {"id": 42, "displayName": "Alice"}
        captured: dict[str, object] = {}

        async def fake_supabase_insert(table, values, *, returning=True):
            captured["table"] = table
            captured["values"] = values
            captured["returning"] = returning
            return [{"id": 99}]

        with patch.object(data, "_resolve_user_id", new=AsyncMock(return_value=owner)), \
             patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_insert", new=fake_supabase_insert):
            result = await data.add_item(
                {
                    "mode": "dispose",
                    "name": "Bottle",
                    "description": "Plastic bottle",
                    "image_url": "data:image/png;base64,abc",
                    "dealt_with_method": "Rinse clean",
                    "eco_rate": 4,
                    "recycle_rate": 3,
                    "overall_score": 78,
                    "material": "plastic",
                    "grade": "Good (B)",
                    "grade_color": "#047857",
                    "grade_advice": "Acceptable",
                    "brand": "Test Brand",
                    "category": "beverage",
                    "weighted_scores": {"a": 60, "b": 70, "c": 80, "d": 90, "e": 50},
                    "schema_id": "food_new",
                    "alternative": None,
                    "precaution": "Keep away from heat",
                    "userId": 42,
                    "userName": "Alice",
                }
            )

        self.assertEqual(result, {"id": 99})
        self.assertEqual(captured["table"], "scan_records")
        self.assertNotIn("grade_color", captured["values"])
        self.assertNotIn("grade_advice", captured["values"])
        self.assertEqual(captured["values"]["user_id"], 42)

    async def test_add_item_requires_a_resolved_user(self):
        async def fake_supabase_insert(*args, **kwargs):
            raise AssertionError("insert should not be attempted without a user")

        with patch.object(data, "_resolve_user_id", new=AsyncMock(return_value=None)), \
             patch.object(data, "supabase_enabled", return_value=True), \
             patch.object(data, "supabase_insert", new=fake_supabase_insert):
            with self.assertRaisesRegex(ValueError, "Login required to save records"):
                await data.add_item(
                    {
                        "mode": "dispose",
                        "name": "Bottle",
                        "overall_score": 78,
                        "schema_id": "food_new",
                    }
                )
