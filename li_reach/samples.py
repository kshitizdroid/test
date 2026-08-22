# -*- coding: utf-8 -*-
"""Bundled sample data + a DemoBackend, so `--demo` can exercise the whole
pipeline (filter, exclude, rank, report) with no LinkedIn, login, or network.

The samples deliberately include roles that should be DROPPED by the
Delhi-NCR-fresher spec (a "Senior" role, a "5+ years" role, a sales post), so
a demo run visibly proves the filtering works — it is not just a happy path.
"""

from __future__ import annotations

from typing import Any, Dict

# job_id -> get_job_details payload (raw innerText, like the real MCP returns)
_DETAILS: Dict[str, Dict[str, Any]] = {
    "4301": {"url": "https://www.linkedin.com/jobs/view/4301/", "sections": {"t":
        "Associate Product Manager\nZomato · Gurugram, India · 3 hours ago\n"
        "18 applicants\nAbout the job\nEntry-level APM role. Fresher friendly."}},
    "4302": {"url": "https://www.linkedin.com/jobs/view/4302/", "sections": {"t":
        "Product Analyst\nPaytm · Noida, India · 1 day ago\n"
        "About the job\nSQL, product metrics. 0-1 years experience."}},
    "4303": {"url": "https://www.linkedin.com/jobs/view/4303/", "sections": {"t":
        "Senior Product Manager\nAcme Corp · Gurugram, India · 2 days ago\n"
        "About the job\n6+ years product experience required."}},
    "4304": {"url": "https://www.linkedin.com/jobs/view/4304/", "sections": {"t":
        "Founder's Office Associate\nStealth Startup · Delhi, India · 5 hours ago\n"
        "About the job\nWork directly with the founder. Freshers welcome."}},
    "4305": {"url": "https://www.linkedin.com/jobs/view/4305/", "sections": {"t":
        "Chief of Staff\nFinTech Co · Gurugram, India · 4 days ago\n"
        "About the job\n0-2 years. Strategy and ops for the CEO."}},
    "4306": {"url": "https://www.linkedin.com/jobs/view/4306/", "sections": {"t":
        "AI Generalist\nGenAI Startup · Noida, India · 6 hours ago\n"
        "About the job\nPrompt engineering, applied ML. 0-2 years."}},
    "4307": {"url": "https://www.linkedin.com/jobs/view/4307/", "sections": {"t":
        "AI Engineer\nBigCo · Gurugram, India · 1 day ago\n"
        "About the job\n5+ years deep learning experience required."}},
}

_SEARCH_JOBS = {
    "job_ids": list(_DETAILS.keys()),
    "sections": {"results": "sample results page"},
    "url": "https://www.linkedin.com/jobs/search/",
}

_SEARCH_POSTS = {
    "url": "https://www.linkedin.com/search/results/content/",
    "sections": {"search_results":
        "Priya Founder\nFounder & CEO at Stealth Startup\n2h\n"
        "We're hiring for our founder's office — freshers welcome, Delhi NCR. DM me!\n"
        "\n"
        "Ravi Kumar\nHead of AI at GenAI Startup\n5h\n"
        "We're hiring AI generalists in Noida — join our team. 0-6 months is fine.\n"
        "\n"
        "Sam Recruiter\nTalent at BigCo\n1d\n"
        "We're hiring senior sales managers. 8+ years only."},
    "references": [
        {"name": "Priya Founder", "url": "https://www.linkedin.com/in/priyafounder"},
        {"name": "Ravi Kumar", "url": "https://www.linkedin.com/in/ravikumar"},
    ],
}


class DemoBackend:
    """Structural Backend that serves the samples above (get_job_details by id)."""

    def __init__(self) -> None:
        self.calls = []

    def call(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append({"tool": tool, "args": args})
        if tool == "search_jobs":
            return dict(_SEARCH_JOBS)
        if tool == "get_job_details":
            return _DETAILS.get(str(args.get("job_id")), {"sections": {}})
        if tool == "search_posts":
            return dict(_SEARCH_POSTS)
        return {"sections": {}, "job_ids": [], "references": [], "url": None}
