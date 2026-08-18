# -*- coding: utf-8 -*-
import json
import os
import tempfile
import unittest

from li_reach import config as C
from li_reach.models import Job, Post
from li_reach.report import render_markdown, write_reports


def _cfg(out_dir, formats):
    return C.from_dict({
        "searches": [{"keywords": "python", "location": "India"}],
        "include_keywords": ["python"],
        "output": {"formats": formats, "dir": out_dir, "top": 10},
    })


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.jobs = [
            Job(job_id="111", title="Python Engineer", company="Acme",
                location="Bengaluru", posted="2 days ago", work_type="remote",
                enriched=True, score=9.6, matched=["python"]),
        ]
        self.posts = [
            Post(author="Jane Dev", role="Eng Manager",
                 url="https://www.linkedin.com/in/janedev",
                 body="We're hiring Python engineers!", posted="2d",
                 score=8.0, matched=["python"]),
        ]

    def test_markdown_contains_job_and_post(self):
        cfg = _cfg("/tmp/unused", ["markdown"])
        md = render_markdown(cfg, self.jobs, self.posts)
        self.assertIn("Python Engineer", md)
        self.assertIn("jobs/view/111", md)
        self.assertIn("Jane Dev", md)
        self.assertIn("We're hiring", md)

    def test_writes_requested_formats(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(d, ["markdown", "json", "csv"])
            written = write_reports(cfg, self.jobs, self.posts)
            self.assertEqual(len(written), 3)
            self.assertTrue(os.path.exists(os.path.join(d, "results.md")))
            self.assertTrue(os.path.exists(os.path.join(d, "jobs.csv")))
            with open(os.path.join(d, "results.json"), encoding="utf-8") as fh:
                payload = json.load(fh)
            self.assertEqual(payload["jobs"][0]["job_id"], "111")
            self.assertEqual(payload["hiring_posts"][0]["author"], "Jane Dev")


if __name__ == "__main__":
    unittest.main()
