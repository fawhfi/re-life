from pathlib import Path
import unittest

import scoring


class ScanUiRequirementsTests(unittest.TestCase):
    def test_disposal_guide_appears_before_weighted_score(self):
        template = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertLess(
            template.index('id="disposal-guide"'),
            template.index('id="weighted-section"'),
        )

    def test_disposal_guide_includes_reuse_row(self):
        template = Path("templates/index.html").read_text(encoding="utf-8")
        source = Path("static/app.js").read_text(encoding="utf-8")

        self.assertIn('id="lbl-disp-reuse"', template)
        self.assertIn('id="disp-reuse"', template)
        self.assertIn("reuse_tip", source)

    def test_rewards_use_generic_provider_names(self):
        rewards_text = "\n".join(
            " ".join(
                str(reward.get(key, ""))
                for key in ("title", "provider", "description")
            )
            for reward in scoring.REWARDS_CATALOG
        )

        self.assertIn("Supermarkets", rewards_text)
        self.assertIn("coffee shop", rewards_text)
        self.assertNotIn("PARKnSHOP", rewards_text)
        self.assertNotIn("Starbucks", rewards_text)

    def test_swap_and_proof_use_one_primary_action(self):
        template = Path("templates/index.html").read_text(encoding="utf-8")
        source = Path("static/app.js").read_text(encoding="utf-8")

        self.assertNotIn('id="lbl-swap"', template)
        self.assertNotIn('onclick="swapAlternative()"', template)
        self.assertIn("function completeSwapFlow()", source)
        self.assertIn('onclick="completeSwapFlow()"', template)
