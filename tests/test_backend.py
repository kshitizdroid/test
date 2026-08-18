# -*- coding: utf-8 -*-
import json
import unittest

from li_reach.backend import McporterBackend, normalize_result


class BuildArgvTest(unittest.TestCase):
    def setUp(self):
        self.b = McporterBackend(command="mcporter", server="linkedin")

    def test_lists_become_comma_separated(self):
        argv = self.b.build_argv(
            "search_jobs",
            {"keywords": "python", "work_type": ["remote", "hybrid"]},
        )
        self.assertIn("keywords=python", argv)
        self.assertIn("work_type=remote,hybrid", argv)

    def test_bool_and_empty_handling(self):
        argv = self.b.build_argv(
            "search_jobs",
            {"keywords": "x", "easy_apply": True, "location": None,
             "experience_level": []},
        )
        self.assertIn("easy_apply=true", argv)
        self.assertFalse(any(a.startswith("location=") for a in argv))
        self.assertFalse(any(a.startswith("experience_level=") for a in argv))

    def test_prefix_is_call(self):
        argv = self.b.build_argv("search_jobs", {"keywords": "x"})
        self.assertEqual(argv[:3], ["mcporter", "call", "linkedin.search_jobs"])


class NormalizeResultTest(unittest.TestCase):
    def test_plain_json_dict(self):
        raw = json.dumps({"url": "u", "sections": {"a": "text"},
                          "job_ids": ["123456"]})
        out = normalize_result(raw)
        self.assertEqual(out["job_ids"], ["123456"])
        self.assertEqual(out["url"], "u")

    def test_mcp_content_envelope(self):
        inner = json.dumps({"job_ids": ["987654321"], "sections": {}})
        raw = json.dumps({"content": [{"type": "text", "text": inner}]})
        out = normalize_result(raw)
        self.assertEqual(out["job_ids"], ["987654321"])

    def test_ids_recovered_from_noisy_text(self):
        raw = "some log line\nhttps://www.linkedin.com/jobs/view/4252026496/\nmore"
        out = normalize_result(raw)
        self.assertEqual(out["job_ids"], ["4252026496"])
        self.assertIn("raw", out["sections"])

    def test_ids_recovered_from_section_blob(self):
        raw = json.dumps({"sections": {"s": "currentJobId=3856789012 hello"}})
        out = normalize_result(raw)
        self.assertEqual(out["job_ids"], ["3856789012"])

    def test_json_slice_out_of_prefixed_output(self):
        raw = 'INFO calling tool\n{"job_ids": ["111111111"], "sections": {}}\n'
        out = normalize_result(raw)
        self.assertEqual(out["job_ids"], ["111111111"])

    def test_empty(self):
        out = normalize_result("")
        self.assertEqual(out["job_ids"], [])
        self.assertEqual(out["sections"], {})


if __name__ == "__main__":
    unittest.main()
