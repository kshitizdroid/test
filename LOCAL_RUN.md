# Run li-reach on your own machine (jobs + hiring posts)

This finds **both** LinkedIn job listings **and** "we're hiring" feed posts for
your spec (Founder's Office / Growth / AI Generalist / Product, 0–1 YoE, Delhi
NCR / Gurugram / Noida), using **your logged-in browser's** LinkedIn session.

## One command

**macOS / Linux**
```bash
git clone https://github.com/kshitizdroid/test.git
cd test && git checkout claude/agent-reach-exploration-4qklqh
bash run_local.sh
```

**Windows (PowerShell)**
```powershell
git clone https://github.com/kshitizdroid/test.git
cd test; git checkout claude/agent-reach-exploration-4qklqh
Set-ExecutionPolicy -Scope Process Bypass
./run_local.ps1
```

The script installs `uv`/`uvx` and `mcporter`, imports your browser's LinkedIn
session (no re-login), runs the search, and opens `out/results.md`.

## Prerequisites (the script checks these)
- **Python 3.10+** (`python3 --version`)
- **Node.js** (`node --version`) — for `mcporter`; install from https://nodejs.org
- A browser (Chrome/Edge/Brave) **logged into LinkedIn**. If the import stalls,
  fully quit the browser and re-run (its cookie store can be locked while open).
  Force a specific browser: `LI_BROWSER=chrome bash run_local.sh`.

## Notes
- Use a **throwaway LinkedIn account** — automated access can get accounts limited.
- First run downloads a Chromium for the MCP (one-time).
- If titles/companies come out blank, the `mcporter` output format differs from
  what the parser expects — paste one raw `mcporter call linkedin.search_jobs …`
  output and it can be tuned.

## Want an AI to drive it on your machine?
Install **Claude Code locally** (desktop app or CLI) on that laptop and open this
repo — that local Claude runs on your computer and can execute `run_local.sh` and
use your browser. (A cloud Claude session cannot reach your machine.)
