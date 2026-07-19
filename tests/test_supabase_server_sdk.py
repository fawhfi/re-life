from pathlib import Path
import json
import unittest


class SupabaseServerSdkTests(unittest.TestCase):
    def test_package_declares_supabase_server_dependency(self):
        pkg = json.loads(Path("package.json").read_text(encoding="utf-8"))

        self.assertEqual(pkg["name"], "re-life-rel")
        self.assertIn("@supabase/server", pkg["dependencies"])

    def test_supabase_config_marks_non_user_functions_without_jwt(self):
        config = Path("supabase/config.toml").read_text(encoding="utf-8")

        self.assertIn("[functions.health]", config)
        self.assertIn("[functions.public_config]", config)
        self.assertIn("[functions.my_records]", config)
        self.assertIn("[functions.admin_users]", config)
        self.assertIn("verify_jwt = true", config)
        self.assertGreaterEqual(config.count("verify_jwt = false"), 3)

    def test_sample_handlers_use_with_supabase_clients(self):
        health = Path("supabase/functions/health/index.ts").read_text(encoding="utf-8")
        public_config = Path("supabase/functions/public_config/index.ts").read_text(encoding="utf-8")
        my_records = Path("supabase/functions/my_records/index.ts").read_text(encoding="utf-8")
        admin_users = Path("supabase/functions/admin_users/index.ts").read_text(encoding="utf-8")

        for source in (health, public_config, my_records, admin_users):
            self.assertIn('withSupabase', source)

        self.assertIn('auth: "none"', health)
        self.assertIn('auth: "publishable"', public_config)
        self.assertIn('auth: "user"', my_records)
        self.assertIn('auth: "secret"', admin_users)
        self.assertIn('ctx.supabase.auth.getUser()', my_records)
        self.assertIn('ctx.supabaseAdmin', admin_users)
