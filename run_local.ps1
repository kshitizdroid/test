# =============================================================================
# run_local.ps1 — ONE command to find LinkedIn jobs + "we're hiring" posts.
# Windows version of run_local.sh. Runs on YOUR PC using YOUR logged-in browser.
#
# Usage (PowerShell):
#   ./run_local.ps1
#   ./run_local.ps1 -Browser chrome
#   ./run_local.ps1 -Config configs/other.yaml
# If blocked, first run:  Set-ExecutionPolicy -Scope Process Bypass
# =============================================================================
param(
  [string]$Config  = "configs/delhi-ncr-fresher.yaml",
  [string]$Browser = "auto"   # most recently used browser with a live LinkedIn session
)

function Say($m){  Write-Host "`n==> $m" -ForegroundColor Cyan }
function Warn($m){ Write-Host "[!] $m" -ForegroundColor Yellow }

# 1) li-reach deps
Say "Installing li-reach deps (PyYAML)…"
python -m pip install -q -r requirements.txt

# 2) uv / uvx
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
  Say "Installing uv (provides uvx)…"
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) { Warn "uvx not on PATH — open a new PowerShell and re-run."; exit 1 }

# 3) Node + mcporter
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Warn "Node.js not found — install from https://nodejs.org then re-run."; exit 1 }
if (-not (Get-Command mcporter -ErrorAction SilentlyContinue)) { Say "Installing mcporter…"; npm install -g mcporter }

# 4) Reuse your logged-in browser session
Say "Connecting to your LinkedIn session from your browser ($Browser)…"
Warn "If this stalls, fully quit Chrome/Edge and re-run (the cookie store can be locked while open)."
try   { uvx mcp-server-linkedin@latest --import-from-browser $Browser }
catch { Warn "Browser import failed — opening a manual login window."; uvx mcp-server-linkedin@latest --login }

# 5) Register the MCP
Say "Registering the LinkedIn MCP…"
mcporter config add linkedin --command uvx --arg mcp-server-linkedin@latest --env UV_HTTP_TIMEOUT=300 --scope home 2>$null

# 6) Verify + run
Say "Verifying setup…"
python -m li_reach --config $Config check
Say "Searching LinkedIn (job listings + 'we're hiring' posts)…"
python -m li_reach --config $Config

# 7) Open the report
if (Test-Path "out/results.md") { Say "Done → out/results.md"; Invoke-Item "out/results.md" }
else { Warn "No results file was written — check the messages above." }
