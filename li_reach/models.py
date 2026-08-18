# -*- coding: utf-8 -*-
"""Result data types shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Job:
    """A single job listing discovered via `linkedin.search_jobs`.

    `job_id` is the only field LinkedIn reliably returns from a search; the
    rest are best-effort, filled in when the job is enriched via
    `linkedin.get_job_details`. `raw` holds the text the filters/ranker act
    on, so scoring stays robust even when field parsing is imperfect.
    """

    job_id: str
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    posted: Optional[str] = None
    work_type: Optional[str] = None
    url: Optional[str] = None
    source_query: str = ""
    raw: str = ""
    enriched: bool = False
    score: float = 0.0
    matched: List[str] = field(default_factory=list)

    @property
    def link(self) -> str:
        """A clickable LinkedIn URL, derived from the id when needed."""
        return self.url or f"https://www.linkedin.com/jobs/view/{self.job_id}/"

    @property
    def display_title(self) -> str:
        return self.title or f"Job {self.job_id}"

    def haystack(self) -> str:
        """Lower-cased text that keyword filters/ranking match against."""
        parts = [self.title, self.company, self.location, self.work_type, self.raw]
        return "\n".join(p for p in parts if p).lower()

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "posted": self.posted,
            "work_type": self.work_type,
            "link": self.link,
            "source_query": self.source_query,
            "enriched": self.enriched,
            "score": round(self.score, 3),
            "matched": self.matched,
        }


@dataclass
class Post:
    """An informal "we're hiring" style feed post via `linkedin.search_posts`."""

    body: str = ""
    author: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    posted: Optional[str] = None
    url: Optional[str] = None
    source_query: str = ""
    score: float = 0.0
    matched: List[str] = field(default_factory=list)

    def haystack(self) -> str:
        parts = [self.body, self.author, self.company, self.role]
        return "\n".join(p for p in parts if p).lower()

    def key(self) -> str:
        """De-dup key: prefer permalink, else author+first line of body."""
        if self.url:
            return self.url
        first_line = (self.body or "").strip().splitlines()[0] if self.body else ""
        return f"{(self.author or '').lower()}::{first_line.lower()[:80]}"

    def to_dict(self) -> dict:
        return {
            "author": self.author,
            "company": self.company,
            "role": self.role,
            "posted": self.posted,
            "url": self.url,
            "body": self.body,
            "source_query": self.source_query,
            "score": round(self.score, 3),
            "matched": self.matched,
        }
