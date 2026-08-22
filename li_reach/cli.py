# -*- coding: utf-8 -*-
"""Command-line entry point.

    python -m li_reach                 # run search with ./config.yaml
    python -m li_reach --config my.yaml
    python -m li_reach --dry-run       # print the mcporter commands, don't call
    python -m li_reach --only posts     # jobs | posts | both (default both)
    python -m li_reach check            # verify mcporter + LinkedIn MCP setup
"""

from __future__ import annotations

import argparse
import shutil
import sys
from typing import List, Optional

from . import __version__, config as config_mod
from .backend import BackendError, McporterBackend
from .pipeline import run_jobs, run_posts
from .report import write_reports

_SETUP_HINT = """\
LinkedIn access goes through agent-reach's stack. One-time setup:

  1. Install uv/uvx:   https://docs.astral.sh/uv/getting-started/installation/
  2. Log in (saves your session):
       uvx mcp-server-linkedin@latest --login
  3. Register with mcporter:
       mcporter config add linkedin --command uvx \\
         --arg mcp-server-linkedin@latest --env UV_HTTP_TIMEOUT=300 --scope home

Use a throwaway LinkedIn account — automated access can get accounts limited.
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="li_reach",
        description="Spec-driven LinkedIn job & hiring-post finder "
        "(built on agent-reach).",
    )
    p.add_argument("command", nargs="?", default="run",
                   choices=["run", "check"], help="run (default) or check setup")
    p.add_argument("-c", "--config", default="config.yaml",
                   help="path to your spec (default: config.yaml)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the mcporter commands instead of calling them")
    p.add_argument("--demo", action="store_true",
                   help="run the full pipeline on bundled sample data "
                        "(no LinkedIn, no login, no setup)")
    p.add_argument("--only", choices=["jobs", "posts", "both"], default="both",
                   help="restrict to jobs or hiring posts (default: both)")
    p.add_argument("-o", "--out", default=None,
                   help="override output.dir from the config")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="echo each backend command")
    p.add_argument("--version", action="version", version=f"li-reach {__version__}")
    return p


def cmd_check(cfg_backend: str) -> int:
    print(f"li-reach {__version__} — checking backend '{cfg_backend}'\n")
    found = shutil.which(cfg_backend)
    if not found:
        print(f"[off] '{cfg_backend}' not found on PATH.\n")
        print(_SETUP_HINT)
        return 1
    print(f"[ok]  {cfg_backend}: {found}")
    if not shutil.which("uvx"):
        print("[warn] uvx not found — the LinkedIn MCP is launched via uvx.")
        print(_SETUP_HINT)
        return 1
    print("[ok]  uvx present.")
    print(
        "\nBackend tooling looks present. This does not verify your LinkedIn "
        "login is still valid — if searches return auth errors, re-run:\n"
        "  uvx mcp-server-linkedin@latest --login"
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        cfg = config_mod.load(args.config)
    except config_mod.ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2

    if args.out:
        cfg.output.dir = args.out

    if args.command == "check":
        return cmd_check(cfg.backend.command)

    if args.demo:
        from .samples import DemoBackend
        print("DEMO MODE — bundled sample data, no LinkedIn / no network.\n")
        backend = DemoBackend()
    else:
        backend = McporterBackend(
            command=cfg.backend.command,
            server=cfg.backend.server,
            timeout=cfg.backend.timeout,
            dry_run=args.dry_run,
            verbose=args.verbose or args.dry_run,
        )

    jobs, posts = [], []
    try:
        if args.only in ("jobs", "both"):
            print("Searching jobs…")
            jobs = run_jobs(cfg, backend)
        if args.only in ("posts", "both") and cfg.hiring_posts.enabled:
            print("Searching hiring posts…")
            posts = run_posts(cfg, backend)
    except BackendError as exc:
        print(f"\nBackend error: {exc}\n", file=sys.stderr)
        print(_SETUP_HINT, file=sys.stderr)
        return 1

    if args.dry_run:
        print("\nDry run complete — no results fetched.")
        return 0

    written = write_reports(cfg, jobs, posts)
    print(f"\nDone. {len(jobs)} jobs, {len(posts)} hiring posts.")
    for path in written:
        print(f"  wrote {path}")
    return 0
