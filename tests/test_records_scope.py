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
        source = Path("static/firebase.js").read_text(encoding="utf-8")
        get_items_block = source[
            source.index("async getItems"):source.index("async deleteItem")
        ]

        guard = "if (!userId && !displayName && !userKey) return [];"

        self.assertRegex(
            get_items_block,
            r"if\s*\(\s*!userId\s*&&\s*!displayName\s*&&\s*!userKey\s*\)\s*return \[\];",
        )
        self.assertLess(
            get_items_block.index(guard),
            get_items_block.index("await FB._ensure();"),
        )
        self.assertRegex(
            get_items_block,
            r"if\s*\(\s*userId\s*\|\|\s*displayName\s*\|\|\s*userKey\s*\)\s*\{",
        )
        self.assertIn("userName: item.userName || null,", source)
