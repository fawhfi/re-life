from pathlib import Path
import unittest


class RecordScopeTests(unittest.TestCase):
    def test_records_load_waits_for_account_init(self):
        source = Path("static/app.js").read_text(encoding="utf-8")

        self.assertNotIn(
            "Promise.all([initAccounts(), loadRecords()])",
            source,
        )
        self.assertIn("await initAccounts();", source)
        self.assertIn("await loadRecords();", source)
        self.assertIn("record.userName = state.currentUser || null;", source)

    def test_get_items_refuses_unauthenticated_reads(self):
        source = Path("static/supabase.js").read_text(encoding="utf-8")

        self.assertIn("function fallbackUserId()", source)
        self.assertIn("function fallbackUserName()", source)
        self.assertIn("if (!userId && !displayName && !userKey) return [];", source)
        self.assertIn("user_id: userId || fallbackUserId() || \"\"", source)
        self.assertIn("display_name: displayName || fallbackUserName() || \"\"", source)
        self.assertIn("user_key: userKey || \"\"", source)
        self.assertIn("async getItems(userId = null, displayName = null, userKey = null)", source)
