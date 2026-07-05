from pathlib import Path
import unittest


AUTH_THEMES = ("light", "dark", "forest", "ocean", "sunset", "midnight")


class AuthThemeTests(unittest.TestCase):
    def test_login_and_register_use_shared_theme_switcher(self):
        for template_name in ("login.html", "register.html"):
            html = Path("templates", template_name).read_text(encoding="utf-8")

            self.assertIn('/static/js/auth-theme.js', html)
            self.assertIn('data-auth-theme-select', html)
            self.assertIn('onchange="applyAuthTheme(this.value)"', html)
            self.assertIn('aria-label="Theme"', html)
            for theme in AUTH_THEMES:
                self.assertIn(f'value="{theme}"', html)

    def test_auth_theme_script_matches_main_theme_storage(self):
        script = Path("static/js/auth-theme.js").read_text(encoding="utf-8")

        self.assertIn("RE_LIFE_THEME", script)
        self.assertIn("applyAuthTheme", script)
        self.assertIn("document.documentElement.setAttribute('data-theme'", script)
        for theme in AUTH_THEMES:
            self.assertIn(f"'{theme}'", script)

    def test_auth_theme_select_is_styled_for_footer(self):
        style = Path("static/style.css").read_text(encoding="utf-8")

        self.assertIn(".auth-theme-select", style)
        self.assertIn(".auth-theme-icon", style)
