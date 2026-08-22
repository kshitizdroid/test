# -*- coding: utf-8 -*-
"""Smoke test for --demo / DemoBackend: the sample run must filter correctly."""

import unittest

from li_reach import config as C
from li_reach.samples import DemoBackend
from li_reach.pipeline import run_jobs, run_posts

SPEC = {
    "searches": [
        {"keywords": "Associate Product Manager", "location": "Gurugram, India"},
        {"keywords": "Founder's Office", "location": "Delhi, India"},
        {"keywords": "AI Generalist", "location": "Noida, India"},
    ],
    "filters": {"date_posted": "past_week", "experience_level": ["internship", "entry"]},
    "exclude_keywords": ["senior", "5+ years"],
    "hiring_posts": {"enabled": True, "phrases": ["we're hiring", "hiring"]},
}


class DemoTest(unittest.TestCase):
    def test_demo_run_filters_seniority(self):
        cfg = C.from_dict(SPEC)
        backend = DemoBackend()
        jobs = run_jobs(cfg, backend)
        posts = run_posts(cfg, backend)

        titles = [j.title for j in jobs]
        self.assertNotIn("Senior Product Manager", titles)   # excluded by "senior"
        self.assertNotIn("AI Engineer", titles)              # excluded by "5+ years"
        self.assertEqual(len(jobs), 5)
        # The two role-matched hiring posts survive; the senior-sales one drops.
        self.assertEqual(len(posts), 2)
        authors = [p.author for p in posts]
        self.assertNotIn("Sam Recruiter", authors)

    def test_jobs_ranked_by_recency(self):
        cfg = C.from_dict(SPEC)
        jobs = run_jobs(cfg, DemoBackend())
        # 3-hours-ago APM should outrank the 4-days-ago Chief of Staff.
        self.assertGreaterEqual(jobs[0].score, jobs[-1].score)


if __name__ == "__main__":
    unittest.main()
