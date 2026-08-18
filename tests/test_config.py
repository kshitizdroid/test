# -*- coding: utf-8 -*-
import unittest

from li_reach import config as C


BASE = {
    "searches": [{"keywords": "software engineer", "location": "India"}],
}


class ConfigTest(unittest.TestCase):
    def test_minimal_ok_with_defaults(self):
        cfg = C.from_dict(BASE)
        self.assertEqual(len(cfg.searches), 1)
        self.assertEqual(cfg.filters.max_pages, 3)
        self.assertTrue(cfg.hiring_posts.enabled)
        self.assertEqual(cfg.output.formats, ["markdown", "json"])

    def test_string_search_shorthand(self):
        cfg = C.from_dict({"searches": ["data scientist"]})
        self.assertEqual(cfg.searches[0].keywords, "data scientist")
        self.assertIsNone(cfg.searches[0].location)

    def test_requires_searches(self):
        with self.assertRaises(C.ConfigError):
            C.from_dict({})

    def test_scalar_coerced_to_list(self):
        cfg = C.from_dict({**BASE, "include_keywords": "python"})
        self.assertEqual(cfg.include_keywords, ["python"])

    def test_invalid_experience_level_rejected(self):
        with self.assertRaises(C.ConfigError):
            C.from_dict({**BASE, "filters": {"experience_level": ["wizard"]}})

    def test_invalid_date_posted_rejected(self):
        with self.assertRaises(C.ConfigError):
            C.from_dict({**BASE, "filters": {"date_posted": "yesterday"}})

    def test_invalid_output_format_rejected(self):
        with self.assertRaises(C.ConfigError):
            C.from_dict({**BASE, "output": {"formats": ["pdf"]}})

    def test_max_pages_bounds(self):
        with self.assertRaises(C.ConfigError):
            C.from_dict({**BASE, "filters": {"max_pages": 99}})

    def test_hiring_post_date_namespace_differs(self):
        # posts use the dashed spelling; the jobs spelling must be rejected here
        with self.assertRaises(C.ConfigError):
            C.from_dict({**BASE, "hiring_posts": {"date_posted": "past_week"}})
        cfg = C.from_dict({**BASE, "hiring_posts": {"date_posted": "past-week"}})
        self.assertEqual(cfg.hiring_posts.date_posted, "past-week")


if __name__ == "__main__":
    unittest.main()
