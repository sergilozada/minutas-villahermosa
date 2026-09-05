from __future__ import annotations

import unittest

from backend.config import STATIC_DIR


class StaticUiTest(unittest.TestCase):
    def test_user_administration_is_not_exposed_in_navigation(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertNotIn('data-route="users"', html)
        self.assertNotIn(">Usuarios<", html)
        self.assertNotIn('api("/api/users")', script)
        self.assertNotIn("renderUsers", script)


if __name__ == "__main__":
    unittest.main()
