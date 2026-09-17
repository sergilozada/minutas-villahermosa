from __future__ import annotations

import unittest
from zipfile import ZipFile

from backend.config import ROOT_DIR, STATIC_DIR


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

    def test_logout_action_is_next_to_new_minute_navigation(self):
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

        create_position = html.index('data-route="new-minute"')
        logout_position = html.index('id="logout-button"')
        self.assertGreater(logout_position, create_position)
        self.assertIn('data-action="logout"', html)
        self.assertIn('button.addEventListener("click", requestLogout)', script)

    def test_firebase_spark_frontend_uses_isolated_project(self):
        script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        schema = STATIC_DIR / "minute_schema.json"

        self.assertIn('projectId: "minutas-villa-hermosa"', script)
        self.assertIn('USE_FIREBASE_BACKEND', script)
        self.assertIn('collection(firebaseRuntime.db, "minutes")', script)
        self.assertIn("new Worker('/minute-generator-worker.js", script)
        self.assertNotIn('minutas-villahermosa.onrender.com', script)
        self.assertTrue(schema.is_file())

    def test_generation_runs_locally_with_timeout_and_progress(self):
        script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        worker = (STATIC_DIR / "minute-generator-worker.js").read_text(encoding="utf-8")

        self.assertIn('DOCUMENT_GENERATION_TIMEOUT_MS = 120_000', script)
        self.assertIn('Cargando motor de documentos', worker)
        self.assertIn('generate_docx(normalized)', worker)
        self.assertIn('/app.js?v=20260916b', html)

    def test_browser_engine_archive_matches_python_sources(self):
        paths = (
            'backend/__init__.py',
            'backend/config.py',
            'backend/schema.py',
            'backend/document_engine.py',
            'config/minute_schema.json',
            'templates/minuta_financiado_template.docx',
            'static/assets/ayt-house-logo.png',
            'static/assets/villa-hermosa-wordmark.png',
        )
        with ZipFile(STATIC_DIR / 'engine.zip') as archive:
            for path in paths:
                self.assertEqual(archive.read(path), (ROOT_DIR / path).read_bytes())


if __name__ == "__main__":
    unittest.main()
