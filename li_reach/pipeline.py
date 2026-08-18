# -*- coding: utf-8 -*-
"""The pipeline: search -> enrich -> filter -> rank, for jobs and posts.

This is the layer agent-reach deliberately leaves to the calling agent. Your
specs (config.yaml) are pushed *down* into `search_jobs` as native filters
where possible (accurate, cheap), then applied again *on top* as keyword /
company post-filters and ranking.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from . import parse
from .config import Config
from .models import Job, Post

# Recency scoring: map common "posted" phrasings to a 0..1 freshness value.
_RECENCY_HINTS = [
    ("hour", 1.0), ("just now", 1.0), ("minute", 1.0),
    ("1 day", 0.9), ("day", 0.8),
    ("1 week", 0.6), ("week", 0.5),
    ("month", 0.2),
]


class Backend:  # structural type; McporterBackend / MockBackend both satisfy it
    def call(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def run_jobs(cfg: Config, backend: Backend) -> List[Job]:
    jobs: Dict[str, Job] = {}  # job_id -> Job, de-duped across all searches

    for search in cfg.searches:
        args = _job_search_args(cfg, search)
        result = backend.call("search_jobs", args)
        query_label = _label(search)
        blob = "\n".join(str(v) for v in (result.get("sections") or {}).values())
        for job_id in result.get("job_ids", []):
            jid = str(job_id)
            if jid not in jobs:
                jobs[jid] = Job(job_id=jid, source_query=query_label, raw=blob)

    ordered = list(jobs.values())

    # Enrich the first N so titles/companies show up and keyword filters can
    # actually bite (a bare search only yields ids + a page blob).
    if cfg.enrichment.enabled and _needs_enrichment(cfg):
        for job in ordered[: cfg.enrichment.top]:
            detail = backend.call("get_job_details", {"job_id": job.job_id})
            enriched = parse.parse_job_detail(detail, job.job_id, job.source_query)
            _merge_job(job, enriched)

    kept = [j for j in ordered if _job_passes(cfg, j)]
    for job in kept:
        job.score, job.matched = _score_job(cfg, job)
    kept.sort(key=lambda j: j.score, reverse=True)
    return kept


def _job_search_args(cfg: Config, search) -> Dict[str, Any]:
    f = cfg.filters
    return {
        "keywords": search.keywords,
        "location": search.location,
        "max_pages": f.max_pages,
        "date_posted": f.date_posted,
        "experience_level": f.experience_level,
        "job_type": f.job_type,
        "work_type": f.work_type,
        "easy_apply": f.easy_apply,
        "sort_by": f.sort_by,
    }


def _needs_enrichment(cfg: Config) -> bool:
    """Enrichment only matters if we have text-level specs to apply/show."""
    return bool(
        cfg.include_keywords
        or cfg.exclude_keywords
        or cfg.exclude_companies
        or cfg.ranking.keyword_weight
        or cfg.ranking.title_match_weight
    )


def _job_passes(cfg: Config, job: Job) -> bool:
    hay = job.haystack()

    # Company exclusions.
    for company in cfg.exclude_companies:
        c = company.lower()
        if (job.company and c in job.company.lower()) or c in hay:
            return False

    # Excluded keywords anywhere.
    for kw in cfg.exclude_keywords:
        if kw.lower() in hay:
            return False

    # Require at least one include keyword — but only for jobs we could
    # actually read (enriched). Un-enriched jobs are kept so we never silently
    # drop everything when enrichment is off.
    if cfg.include_keywords and job.enriched:
        if not any(kw.lower() in hay for kw in cfg.include_keywords):
            return False
    return True


def _score_job(cfg: Config, job: Job) -> Tuple[float, List[str]]:
    hay = job.haystack()
    title = (job.title or "").lower()
    score = 0.0
    matched: List[str] = []
    for kw in cfg.include_keywords:
        k = kw.lower()
        if k in hay:
            score += cfg.ranking.keyword_weight
            matched.append(kw)
            if k in title:
                score += cfg.ranking.title_match_weight
    score += cfg.ranking.recency_weight * _recency(job.posted)
    return score, matched


# ---------------------------------------------------------------------------
# Hiring posts
# ---------------------------------------------------------------------------

def run_posts(cfg: Config, backend: Backend) -> List[Post]:
    if not cfg.hiring_posts.enabled:
        return []

    posts: Dict[str, Post] = {}
    role_terms = _role_terms(cfg)

    for query in _post_queries(cfg):
        result = backend.call(
            "search_posts",
            {
                "keywords": query,
                "date_posted": cfg.hiring_posts.date_posted,
                "max_pages": cfg.hiring_posts.max_pages,
            },
        )
        for post in parse.parse_posts(result, query):
            if not _post_passes(cfg, post, role_terms):
                continue
            key = post.key()
            if key not in posts:
                post.score, post.matched = _score_post(cfg, post, role_terms)
                posts[key] = post

    ranked = sorted(posts.values(), key=lambda p: p.score, reverse=True)
    return ranked


def _post_queries(cfg: Config) -> List[str]:
    """Combine each role keyword with each hiring phrase, e.g. 'python hiring'."""
    roles = [s.keywords for s in cfg.searches]
    queries: List[str] = []
    for role in roles:
        for phrase in cfg.hiring_posts.phrases:
            queries.append(f"{role} {phrase}".strip())
    # De-dup while preserving order.
    seen, out = set(), []
    for q in queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out


def _post_passes(cfg: Config, post: Post, role_terms: List[str]) -> bool:
    hay = post.haystack()
    for kw in cfg.exclude_keywords:
        if kw.lower() in hay:
            return False
    for company in cfg.exclude_companies:
        if company.lower() in hay:
            return False
    if cfg.hiring_posts.require_role_match and role_terms:
        if not any(term in hay for term in role_terms):
            return False
    return True


def _score_post(cfg: Config, post: Post, role_terms: List[str]) -> Tuple[float, List[str]]:
    hay = post.haystack()
    score = 0.0
    matched: List[str] = []
    for term in role_terms:
        if term in hay:
            score += cfg.ranking.keyword_weight
            matched.append(term)
    for phrase in cfg.hiring_posts.phrases:
        if phrase.lower() in hay:
            score += 1.0
    score += cfg.ranking.recency_weight * _recency(post.posted)
    return score, matched


def _role_terms(cfg: Config) -> List[str]:
    terms = set(k.lower() for k in cfg.include_keywords)
    for s in cfg.searches:
        for token in s.keywords.lower().split():
            if len(token) > 2:
                terms.add(token)
    return sorted(terms)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _recency(posted: str | None) -> float:
    if not posted:
        return 0.0
    low = posted.lower()
    for hint, value in _RECENCY_HINTS:
        if hint in low:
            return value
    return 0.0


def _label(search) -> str:
    return f"{search.keywords}" + (f" @ {search.location}" if search.location else "")


def _merge_job(base: Job, enriched: Job) -> None:
    base.title = enriched.title or base.title
    base.company = enriched.company or base.company
    base.location = enriched.location or base.location
    base.posted = enriched.posted or base.posted
    base.work_type = enriched.work_type or base.work_type
    base.url = enriched.url or base.url
    base.raw = enriched.raw or base.raw
    base.enriched = True
