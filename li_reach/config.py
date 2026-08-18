# -*- coding: utf-8 -*-
"""Load and validate the user's search specification (config.yaml).

The config is the whole point of this tool: it captures *your* criteria once,
so a single `python -m li_reach` run reproduces the same targeted search.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency guard
    raise SystemExit(
        "PyYAML is required. Install it with:  pip install pyyaml"
    ) from exc


class ConfigError(ValueError):
    """Raised when config.yaml is missing required fields or has bad values."""


# Allowed values mirror mcp-server-linkedin's search_jobs / search_posts args.
DATE_POSTED_JOBS = {"past_hour", "past_24_hours", "past_week", "past_month"}
DATE_POSTED_POSTS = {"past-24h", "past-week", "past-month"}
EXPERIENCE_LEVELS = {
    "internship", "entry", "associate", "mid_senior", "director", "executive",
}
JOB_TYPES = {
    "full_time", "part_time", "contract", "temporary", "volunteer",
    "internship", "other",
}
WORK_TYPES = {"on_site", "remote", "hybrid"}
SORT_BY = {"date", "relevance"}


@dataclass
class Search:
    keywords: str
    location: Optional[str] = None


@dataclass
class Filters:
    date_posted: Optional[str] = None
    experience_level: List[str] = field(default_factory=list)
    job_type: List[str] = field(default_factory=list)
    work_type: List[str] = field(default_factory=list)
    easy_apply: bool = False
    sort_by: Optional[str] = None
    max_pages: int = 3


@dataclass
class HiringPosts:
    enabled: bool = True
    phrases: List[str] = field(
        default_factory=lambda: ["we're hiring", "hiring", "join our team"]
    )
    date_posted: Optional[str] = "past-week"
    max_pages: int = 2
    require_role_match: bool = True


@dataclass
class Ranking:
    keyword_weight: float = 3.0
    title_match_weight: float = 5.0
    recency_weight: float = 2.0


@dataclass
class Enrichment:
    enabled: bool = True
    top: int = 20


@dataclass
class Backend:
    command: str = "mcporter"
    server: str = "linkedin"
    timeout: int = 300


@dataclass
class Output:
    formats: List[str] = field(default_factory=lambda: ["markdown", "json"])
    dir: str = "./out"
    top: int = 50


@dataclass
class Config:
    searches: List[Search]
    filters: Filters = field(default_factory=Filters)
    include_keywords: List[str] = field(default_factory=list)
    exclude_keywords: List[str] = field(default_factory=list)
    exclude_companies: List[str] = field(default_factory=list)
    hiring_posts: HiringPosts = field(default_factory=HiringPosts)
    ranking: Ranking = field(default_factory=Ranking)
    enrichment: Enrichment = field(default_factory=Enrichment)
    backend: Backend = field(default_factory=Backend)
    output: Output = field(default_factory=Output)


def _as_list(value: Any) -> List[str]:
    """Accept a scalar or list in YAML and normalise to a list of strings."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()]


def _check_choices(name: str, values: List[str], allowed: set) -> None:
    bad = [v for v in values if v not in allowed]
    if bad:
        raise ConfigError(
            f"{name}: invalid value(s) {bad}. Allowed: {sorted(allowed)}"
        )


def load(path: str) -> Config:
    """Parse and validate config.yaml at `path`, returning a Config."""
    if not os.path.exists(path):
        raise ConfigError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        data: Dict[str, Any] = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ConfigError("Top level of config.yaml must be a mapping.")

    return from_dict(data)


def from_dict(data: Dict[str, Any]) -> Config:
    """Build a Config from an already-parsed mapping (used by tests too)."""
    raw_searches = data.get("searches") or []
    if not raw_searches:
        raise ConfigError(
            "config.yaml must define at least one entry under 'searches'."
        )
    searches: List[Search] = []
    for i, item in enumerate(raw_searches):
        if isinstance(item, str):
            searches.append(Search(keywords=item))
            continue
        if not isinstance(item, dict) or not item.get("keywords"):
            raise ConfigError(f"searches[{i}] must have a 'keywords' field.")
        searches.append(
            Search(keywords=str(item["keywords"]), location=item.get("location"))
        )

    f = data.get("filters") or {}
    filters = Filters(
        date_posted=f.get("date_posted"),
        experience_level=_as_list(f.get("experience_level")),
        job_type=_as_list(f.get("job_type")),
        work_type=_as_list(f.get("work_type")),
        easy_apply=bool(f.get("easy_apply", False)),
        sort_by=f.get("sort_by"),
        max_pages=int(f.get("max_pages", 3)),
    )
    if filters.date_posted is not None:
        _check_choices("filters.date_posted", [filters.date_posted], DATE_POSTED_JOBS)
    _check_choices("filters.experience_level", filters.experience_level, EXPERIENCE_LEVELS)
    _check_choices("filters.job_type", filters.job_type, JOB_TYPES)
    _check_choices("filters.work_type", filters.work_type, WORK_TYPES)
    if filters.sort_by is not None:
        _check_choices("filters.sort_by", [filters.sort_by], SORT_BY)
    if not 1 <= filters.max_pages <= 10:
        raise ConfigError("filters.max_pages must be between 1 and 10.")

    hp = data.get("hiring_posts") or {}
    hiring = HiringPosts(
        enabled=bool(hp.get("enabled", True)),
        phrases=_as_list(hp.get("phrases")) or HiringPosts().phrases,
        date_posted=hp.get("date_posted", "past-week"),
        max_pages=int(hp.get("max_pages", 2)),
        require_role_match=bool(hp.get("require_role_match", True)),
    )
    if hiring.date_posted is not None:
        _check_choices("hiring_posts.date_posted", [hiring.date_posted], DATE_POSTED_POSTS)
    if not 1 <= hiring.max_pages <= 10:
        raise ConfigError("hiring_posts.max_pages must be between 1 and 10.")

    r = data.get("ranking") or {}
    ranking = Ranking(
        keyword_weight=float(r.get("keyword_weight", 3.0)),
        title_match_weight=float(r.get("title_match_weight", 5.0)),
        recency_weight=float(r.get("recency_weight", 2.0)),
    )

    e = data.get("enrichment") or {}
    enrichment = Enrichment(
        enabled=bool(e.get("enabled", True)),
        top=int(e.get("top", 20)),
    )

    b = data.get("backend") or {}
    backend = Backend(
        command=str(b.get("command", "mcporter")),
        server=str(b.get("server", "linkedin")),
        timeout=int(b.get("timeout", 300)),
    )

    o = data.get("output") or {}
    output = Output(
        formats=_as_list(o.get("formats")) or ["markdown", "json"],
        dir=str(o.get("dir", "./out")),
        top=int(o.get("top", 50)),
    )
    for fmt in output.formats:
        if fmt not in {"markdown", "json", "csv"}:
            raise ConfigError(f"output.formats: unknown format '{fmt}'.")

    return Config(
        searches=searches,
        filters=filters,
        include_keywords=_as_list(data.get("include_keywords")),
        exclude_keywords=_as_list(data.get("exclude_keywords")),
        exclude_companies=_as_list(data.get("exclude_companies")),
        hiring_posts=hiring,
        ranking=ranking,
        enrichment=enrichment,
        backend=backend,
        output=output,
    )
