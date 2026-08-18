# -*- coding: utf-8 -*-
"""Render the ranked jobs + hiring posts to markdown / json / csv files."""

from __future__ import annotations

import csv
import datetime as _dt
import json
import os
from typing import List

from .config import Config
from .models import Job, Post


def write_reports(cfg: Config, jobs: List[Job], posts: List[Post]) -> List[str]:
    os.makedirs(cfg.output.dir, exist_ok=True)
    jobs = jobs[: cfg.output.top]
    posts = posts[: cfg.output.top]
    written: List[str] = []

    if "markdown" in cfg.output.formats:
        path = os.path.join(cfg.output.dir, "results.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(cfg, jobs, posts))
        written.append(path)

    if "json" in cfg.output.formats:
        path = os.path.join(cfg.output.dir, "results.json")
        payload = {
            "generated_at": _now(),
            "spec": {
                "searches": [
                    {"keywords": s.keywords, "location": s.location}
                    for s in cfg.searches
                ],
                "include_keywords": cfg.include_keywords,
                "exclude_keywords": cfg.exclude_keywords,
                "exclude_companies": cfg.exclude_companies,
            },
            "jobs": [j.to_dict() for j in jobs],
            "hiring_posts": [p.to_dict() for p in posts],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        written.append(path)

    if "csv" in cfg.output.formats:
        path = os.path.join(cfg.output.dir, "jobs.csv")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                ["score", "title", "company", "location", "posted", "link",
                 "matched", "source_query"]
            )
            for j in jobs:
                writer.writerow(
                    [round(j.score, 2), j.display_title, j.company or "",
                     j.location or "", j.posted or "", j.link,
                     ", ".join(j.matched), j.source_query]
                )
        written.append(path)

    return written


def render_markdown(cfg: Config, jobs: List[Job], posts: List[Post]) -> str:
    lines: List[str] = []
    lines.append("# LinkedIn results — li-reach")
    lines.append("")
    lines.append(f"_Generated {_now()}_")
    lines.append("")
    lines.append("## Your spec")
    for s in cfg.searches:
        loc = f" @ {s.location}" if s.location else ""
        lines.append(f"- **{s.keywords}**{loc}")
    if cfg.include_keywords:
        lines.append(f"- must include: `{', '.join(cfg.include_keywords)}`")
    if cfg.exclude_keywords:
        lines.append(f"- exclude keywords: `{', '.join(cfg.exclude_keywords)}`")
    if cfg.exclude_companies:
        lines.append(f"- exclude companies: `{', '.join(cfg.exclude_companies)}`")
    lines.append("")

    lines.append(f"## Jobs ({len(jobs)})")
    lines.append("")
    if not jobs:
        lines.append("_No jobs matched._")
    else:
        for i, j in enumerate(jobs, 1):
            meta = " · ".join(
                x for x in (j.company, j.location, j.work_type, j.posted) if x
            )
            tags = f"  \n  matched: `{', '.join(j.matched)}`" if j.matched else ""
            note = "" if j.enriched else "  _(not enriched)_"
            lines.append(
                f"{i}. **[{j.display_title}]({j.link})** "
                f"— score {j.score:.1f}{note}"
            )
            if meta:
                lines.append(f"   {meta}")
            if tags:
                lines.append(f"  {tags.strip()}")
    lines.append("")

    lines.append(f"## \"We're hiring\" posts ({len(posts)})")
    lines.append("")
    if not posts:
        lines.append("_No hiring posts matched (or disabled)._")
    else:
        for i, p in enumerate(posts, 1):
            head = p.author or "Unknown author"
            link = f"[{head}]({p.url})" if p.url else head
            lines.append(f"{i}. **{link}** — score {p.score:.1f}")
            if p.role:
                lines.append(f"   {p.role}")
            if p.posted:
                lines.append(f"   _{p.posted}_")
            snippet = _snippet(p.body)
            if snippet:
                lines.append(f"   > {snippet}")
    lines.append("")
    lines.append("---")
    lines.append(
        "_Built on agent-reach's LinkedIn channel "
        "(mcp-server-linkedin via mcporter)._"
    )
    return "\n".join(lines) + "\n"


def _snippet(body: str, limit: int = 240) -> str:
    text = " ".join((body or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
