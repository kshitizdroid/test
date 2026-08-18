# -*- coding: utf-8 -*-
import unittest

from li_reach import config as C
from li_reach.backend import MockBackend
from li_reach.pipeline import run_jobs, run_posts

DETAIL_111 = {
    "url": "https://www.linkedin.com/jobs/view/111/",
    "sections": {
        "top": (
            "Senior Python Engineer\n"
            "Acme · Bengaluru, India · 2 days ago\n"
            "120 applicants\n"
            "About the job\n"
            "We need strong Python, API and backend skills. Remote friendly."
        )
    },
}
DETAIL_222 = {
    "url": "https://www.linkedin.com/jobs/view/222/",
    "sections": {
        "top": (
            "Sales Manager\n"
            "BadStaffing Co · Mumbai · 1 week ago\n"
            "About the job\n"
            "Drive sales targets across the region."
        )
    },
}

POSTS_RESULT = {
    "url": "https://www.linkedin.com/search/results/content/",
    "sections": {
        "search_results": (
            "Jane Dev\n"
            "Engineering Manager at Acme\n"
            "2d\n"
            "We're hiring Python backend engineers! Join our team.\n"
            "\n"
            "Bob Sales\n"
            "Sales Lead\n"
            "3d\n"
            "We're hiring account executives for our sales org."
        )
    },
    "references": [
        {"name": "Jane Dev", "url": "https://www.linkedin.com/in/janedev"},
    ],
}


class RunJobsTest(unittest.TestCase):
    def _cfg(self, **over):
        data = {
            "searches": [
                {"keywords": "python", "location": "India"},
                {"keywords": "backend", "location": "Remote"},
            ],
            "include_keywords": ["python"],
            "exclude_keywords": ["sales"],
            "exclude_companies": ["BadStaffing"],
            "hiring_posts": {"enabled": False},
        }
        data.update(over)
        return C.from_dict(data)

    def test_dedupe_enrich_filter_and_rank(self):
        backend = MockBackend({
            "search_jobs": {"job_ids": ["111", "222"],
                            "sections": {"results": "page blob"}},
            "get_job_details": [DETAIL_111, DETAIL_222],
        })
        jobs = run_jobs(self._cfg(), backend)

        # 111 and 222 are deduped across the two searches; 222 is dropped for
        # matching an excluded keyword ("sales") and company ("BadStaffing").
        self.assertEqual([j.job_id for j in jobs], ["111"])
        job = jobs[0]
        self.assertEqual(job.title, "Senior Python Engineer")
        self.assertEqual(job.company, "Acme")
        self.assertEqual(job.location, "Bengaluru, India")
        self.assertIn("python", job.matched)
        self.assertGreater(job.score, 0)
        self.assertTrue(job.link.endswith("/jobs/view/111/"))

    def test_unenriched_jobs_are_kept(self):
        # Enrichment off + include_keywords set: we can't read the jobs, so we
        # keep them rather than silently dropping everything.
        cfg = self._cfg(enrichment={"enabled": False})
        backend = MockBackend({
            "search_jobs": {"job_ids": ["111", "222"], "sections": {}},
        })
        jobs = run_jobs(cfg, backend)
        self.assertEqual(sorted(j.job_id for j in jobs), ["111", "222"])
        # get_job_details was never called.
        self.assertFalse(any(c["tool"] == "get_job_details" for c in backend.calls))


class RunPostsTest(unittest.TestCase):
    def _cfg(self):
        return C.from_dict({
            "searches": [{"keywords": "python backend"}],
            "include_keywords": ["python"],
            "exclude_keywords": ["sales"],
            "hiring_posts": {
                "enabled": True,
                "phrases": ["we're hiring", "hiring"],
                "date_posted": "past-week",
                "max_pages": 1,
            },
        })

    def test_hiring_posts_filtered_and_deduped(self):
        backend = MockBackend({"search_posts": POSTS_RESULT})
        posts = run_posts(self._cfg(), backend)

        # Jane's Python/backend post is kept once (deduped across the two
        # phrase queries); Bob's sales post is dropped.
        self.assertEqual(len(posts), 1)
        post = posts[0]
        self.assertEqual(post.author, "Jane Dev")
        self.assertEqual(post.url, "https://www.linkedin.com/in/janedev")
        self.assertIn("python", post.matched)
        self.assertGreater(post.score, 0)

    def test_two_phrase_queries_issued(self):
        backend = MockBackend({"search_posts": POSTS_RESULT})
        run_posts(self._cfg(), backend)
        queries = [c["args"]["keywords"] for c in backend.calls]
        self.assertEqual(
            queries,
            ["python backend we're hiring", "python backend hiring"],
        )


if __name__ == "__main__":
    unittest.main()
