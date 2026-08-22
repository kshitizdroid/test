#!/usr/bin/env bash
# =============================================================================
# run_local.sh — ONE command to find LinkedIn jobs + "we're hiring" posts.
#
# Runs on YOUR machine, using YOUR logged-in browser's LinkedIn session.
# Sets up uv/uvx + mcporter + the LinkedIn MCP, then runs li-reach against
# your spec (Founder's Office / Growth / AI Generalist / Product, 0-1 YoE,
# Delhi NCR / Gurugram / Noida) and writes out/results.md.
#
# Usage:   bash run_local.sh
#          LI_BROWSER=chrome bash run_local.sh      # force a browser
#          bash run_local.sh configs/other.yaml     # a different spec
# =============================================================================
set -u

CONFIG="${1:-configs/delhi-ncr-fresher.yaml}"
BROWSER="${LI_BROWSER:-auto}"   # auto = most recently used browser with a live LinkedIn session

say(){  printf "\n\033[1;36m==> %s\033[0m\n" "$1"; }
warn(){ printf "\033[1;33m[!] %s\033[0m\n" "$1"; }

# 1) li-reach's own Python deps -----------------------------------------------
say "Installing li-reach deps (PyYAML)…"
python3 -m pip install -q -r requirements.txt || { warn "pip failed — is python3 (3.10+) installed?"; exit 1; }

# 2) uv / uvx (runs the LinkedIn MCP on demand) -------------------------------
if ! command -v uvx >/dev/null 2>&1; then
  say "Installing uv (provides uvx)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
command -v uvx >/dev/null 2>&1 || { warn "uvx not on PATH — open a new terminal (or add ~/.local/bin to PATH) and re-run."; exit 1; }

# 3) Node.js + mcporter (the bridge li-reach calls) ---------------------------
command -v node >/dev/null 2>&1 || { warn "Node.js not found — install it from https://nodejs.org then re-run."; exit 1; }
if ! command -v mcporter >/dev/null 2>&1; then
  say "Installing mcporter…"
  npm install -g mcporter || { warn "'npm install -g mcporter' failed (try sudo, or fix npm perms)."; exit 1; }
fi

# 4) Reuse your logged-in browser's LinkedIn session --------------------------
say "Connecting to your LinkedIn session from your browser ($BROWSER)…"
warn "If this stalls on Chrome/Edge, fully quit the browser and re-run (the cookie DB can be locked while open)."
if ! uvx mcp-server-linkedin@latest --import-from-browser "$BROWSER"; then
  warn "Browser import didn't work — opening a manual login window instead."
  uvx mcp-server-linkedin@latest --login
fi

# 5) Register the MCP with mcporter (safe to re-run) --------------------------
say "Registering the LinkedIn MCP…"
mcporter config add linkedin --command uvx --arg mcp-server-linkedin@latest --env UV_HTTP_TIMEOUT=300 --scope home 2>/dev/null \
  || warn "linkedin already registered — continuing."

# 6) Verify, then run (jobs + hiring posts) -----------------------------------
say "Verifying setup…"
python3 -m li_reach --config "$CONFIG" check || true
say "Searching LinkedIn (job listings + 'we're hiring' posts)…"
python3 -m li_reach --config "$CONFIG"

# 7) Open the report ----------------------------------------------------------
OUT="out/results.md"
if [ -f "$OUT" ]; then
  say "Done → $OUT"
  case "$(uname -s)" in
    Darwin) open "$OUT" 2>/dev/null || true ;;
    Linux)  xdg-open "$OUT" 2>/dev/null || true ;;
  esac
else
  warn "No results file was written — check the messages above."
fi
