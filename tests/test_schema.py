from pathlib import Path
import unittest


class SchemaTests(unittest.TestCase):
    def test_supabase_schema_contains_foreign_key(self):
        schema = Path("supabase_schema.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.app_users", schema)
        self.assertIn("create table if not exists public.scan_records", schema)
        self.assertIn("create table if not exists public.auth_codes", schema)
        self.assertIn("create table if not exists public.news_cache", schema)
        self.assertIn(
            "user_id bigint not null references public.app_users(id) on delete cascade",
            schema,
        )
        self.assertIn("public_id text not null unique", schema)
        self.assertIn("unique (purpose, email)", schema)

    def test_supabase_schema_includes_scan_image_bucket(self):
        schema = Path("supabase_schema.sql").read_text(encoding="utf-8")

        self.assertIn("insert into storage.buckets", schema)
        self.assertIn("'scan-images'", schema)
        self.assertIn("service_role can manage scan images", schema)
