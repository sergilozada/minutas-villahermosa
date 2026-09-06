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

    def test_topbar_uses_compact_role_chip_without_duplicate_create_action(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        styles = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

        self.assertNotIn('id="quick-create"', html)
        self.assertNotIn("elements.quickCreate", script)
        self.assertIn('class="profile-chip__dot"', html)
        self.assertIn('<strong id="profile-name">Admin</strong>', html)
        self.assertIn('window.self !== window.top', script)
        self.assertIn('.is-embedded .topbar__actions', styles)

    def test_internal_navigation_is_a_compact_toolbar_not_a_second_sidebar(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        self.assertNotIn('<aside class="sidebar"', html)
        self.assertNotIn('id="sidebar-toggle"', html)
        self.assertNotIn("elements.sidebarToggle", script)
        self.assertNotIn("elements.sidebarCurrent", script)
        self.assertIn('class="section-nav"', html)
        self.assertIn('class="section-nav__item is-active"', html)

    def test_firebase_spark_frontend_uses_isolated_project(self):
        script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        schema = STATIC_DIR / "minute_schema.json"

        self.assertIn('projectId: "minutas-villa-hermosa"', script)
        self.assertIn('USE_FIREBASE_BACKEND', script)
        self.assertIn('collection(firebaseRuntime.db, "minutes")', script)
        self.assertIn('https://minutas-villahermosa.onrender.com/api/firebase/generate', script)
        self.assertTrue(schema.is_file())


if __name__ == "__main__":
    unittest.main()
