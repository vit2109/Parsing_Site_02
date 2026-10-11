from __future__ import annotations

import unittest

from parsing_site.test_server import health, test_map


class TestMapServerTest(unittest.TestCase):
    def test_page_contains_tracking_contract(self) -> None:
        response = test_map()
        page = response.path.read_text(encoding="utf-8")
        self.assertIn('class="leaflet-container"', page)
        self.assertIn("test-map.js", page)

    def test_health(self) -> None:
        self.assertEqual(health(), {"status": "ok"})
