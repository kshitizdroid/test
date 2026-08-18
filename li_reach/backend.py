# -*- coding: utf-8 -*-
"""Backend layer: turn a (tool, args) call into a normalised result dict.

The real backend shells out to the exact command agent-reach documents:

    mcporter call linkedin.search_jobs keywords="..." location="..." ...

`mcp-server-linkedin` returns a dict like:

    {"url": ..., "sections": {name: raw_text}, "job_ids": [...],
     "references": [...], "section_errors": {...}}

but `mcporter` may wrap or pretty-print that, so `normalize_result` is
deliberately tolerant: JSON, MCP content envelopes, or plain text all reduce
to the same shape. Field parsing lives in parse.py, not here.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from typing import Any, Dict, List, Optional

# Matches numeric LinkedIn job ids however they appear in output.
_JOB_ID_RE = re.compile(r"(?:jobs/view/|currentJobId=|\"job_id\"\s*:\s*\")(\d{6,})")
_LOOSE_ID_RE = re.compile(r"\b(\d{8,12})\b")


class BackendError(RuntimeError):
    """Raised when the underlying MCP call fails."""


def _stringify_args(args: Dict[str, Any]) -> Dict[str, str]:
    """Render arg values the way the mcporter CLI expects them.

    Lists become comma-separated (search_jobs takes comma-separated filters),
    booleans become 'true'/'false', and empty/None values are dropped so we
    never send `location=` with nothing after it.
    """
    out: Dict[str, str] = {}
    for key, value in args.items():
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        elif isinstance(value, (list, tuple)):
            joined = ",".join(str(v) for v in value if str(v) != "")
            if joined:
                out[key] = joined
        else:
            out[key] = str(value)
    return out


class McporterBackend:
    """Calls `mcporter call <server>.<tool> k=v ...` and normalises stdout."""

    def __init__(
        self,
        command: str = "mcporter",
        server: str = "linkedin",
        timeout: int = 300,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> None:
        self.command = command
        self.server = server
        self.timeout = timeout
        self.dry_run = dry_run
        self.verbose = verbose

    def build_argv(self, tool: str, args: Dict[str, Any]) -> List[str]:
        argv = [self.command, "call", f"{self.server}.{tool}"]
        for key, value in _stringify_args(args).items():
            argv.append(f"{key}={value}")
        return argv

    def call(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        argv = self.build_argv(tool, args)
        printable = " ".join(shlex.quote(a) for a in argv)
        if self.dry_run:
            print(f"  DRY-RUN  {printable}")
            return {"sections": {}, "job_ids": [], "references": [], "url": None}
        if self.verbose:
            print(f"  $ {printable}")
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except FileNotFoundError as exc:
            raise BackendError(
                f"'{self.command}' not found on PATH. Install it and configure the "
                f"LinkedIn MCP first (see README / `python -m li_reach check`)."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise BackendError(f"{tool} timed out after {self.timeout}s") from exc
        if proc.returncode != 0:
            raise BackendError(
                f"{tool} failed (exit {proc.returncode}): "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
        return normalize_result(proc.stdout)


class MockBackend:
    """Test/offline backend. Serves canned dicts keyed by tool name.

    `responses` maps a tool name to either a single dict or a list of dicts
    (consumed in order, so successive calls to the same tool can differ).
    """

    def __init__(self, responses: Dict[str, Any]) -> None:
        self._responses = {k: list(v) if isinstance(v, list) else [v]
                           for k, v in responses.items()}
        self.calls: List[Dict[str, Any]] = []

    def call(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append({"tool": tool, "args": args})
        queue = self._responses.get(tool)
        if not queue:
            return {"sections": {}, "job_ids": [], "references": [], "url": None}
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        return normalize_result(item)


def _coerce_mcp_envelope(obj: Any) -> Optional[str]:
    """If `obj` is an MCP content envelope, pull out the text payload."""
    if isinstance(obj, dict) and isinstance(obj.get("content"), list):
        texts = [
            c.get("text", "")
            for c in obj["content"]
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        if texts:
            return "\n".join(texts)
    return None


def normalize_result(raw: Any) -> Dict[str, Any]:
    """Reduce whatever the backend returned to a stable result dict."""
    empty = {"sections": {}, "job_ids": [], "references": [], "url": None,
             "section_errors": {}}

    # Already a dict (MockBackend, or a caller that pre-parsed).
    if isinstance(raw, dict):
        text_payload = _coerce_mcp_envelope(raw)
        if text_payload is not None:
            return normalize_result(text_payload)
        return _fill(raw, empty)

    if not isinstance(raw, str):
        return empty

    text = raw.strip()
    if not text:
        return empty

    # Try strict JSON, then a best-effort {...} slice out of noisy stdout.
    for candidate in (text, _slice_json(text)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        env = _coerce_mcp_envelope(parsed)
        if env is not None:
            return normalize_result(env)
        if isinstance(parsed, dict):
            return _fill(parsed, empty)

    # Plain text: keep it, and still recover any job ids we can see.
    result = dict(empty)
    result["sections"] = {"raw": text}
    result["job_ids"] = _extract_ids(text)
    return result


def _slice_json(text: str) -> Optional[str]:
    start = text.find("{")
    end = text.rfind("}")
    if 0 <= start < end:
        return text[start : end + 1]
    return None


def _extract_ids(text: str) -> List[str]:
    ids = _JOB_ID_RE.findall(text)
    if not ids:
        ids = _LOOSE_ID_RE.findall(text)
    seen: Dict[str, None] = {}
    for i in ids:
        seen.setdefault(i, None)
    return list(seen.keys())


def _fill(parsed: Dict[str, Any], empty: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(empty)
    result.update({k: v for k, v in parsed.items() if v is not None})
    result.setdefault("sections", {})
    # Recover ids from section text if the server didn't hand us a list.
    if not result.get("job_ids"):
        blob = "\n".join(str(v) for v in (result.get("sections") or {}).values())
        result["job_ids"] = _extract_ids(blob)
    # Normalise types.
    if not isinstance(result.get("sections"), dict):
        result["sections"] = {"raw": str(result["sections"])}
    if not isinstance(result.get("job_ids"), list):
        result["job_ids"] = []
    if not isinstance(result.get("references"), list):
        result["references"] = []
    return result
