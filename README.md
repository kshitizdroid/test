# li-reach

A **spec-driven LinkedIn job & "we're hiring" finder**, built on top of
[agent-reach](https://github.com/Panniantong/agent-reach)'s LinkedIn channel.

You write your search criteria once in `config.yaml`; one command then pulls
LinkedIn job listings **and** informal "we're hiring" feed posts, filters them
to your spec, ranks them, and writes a clean Markdown/JSON/CSV report.

---

## How this relates to agent-reach

agent-reach is a **router**, not a scraper. For LinkedIn it doesn't fetch
anything itself — it detects and wires up the third-party
[`mcp-server-linkedin`](https://github.com/stickerdaniel/linkedin-mcp-server)
MCP (run via `uvx`, registered through `mcporter`), which does the
authenticated scraping using **your saved LinkedIn login**. agent-reach then
leaves the actual "search, filter, decide" work to the calling agent.

`li-reach` **is that missing layer.** It shells out to the exact commands
agent-reach documents —

```bash
mcporter call linkedin.search_jobs  keywords="..." location="..." ...
mcporter call linkedin.search_posts keywords="... we're hiring" ...
```

— and adds everything on top: pushing your spec down into LinkedIn's native
filters, de-duplicating, keyword/company filtering, ranking, and reporting.

```
  your config.yaml
        │
        ▼
  li-reach  ──►  mcporter  ──►  mcp-server-linkedin  ──►  LinkedIn (your login)
        ▲                                                        │
        └──────────── filter · rank · report ◄──────────────────┘
```

---

## ⚠️ Read this first

- **It runs on *your* machine, not in the cloud.** LinkedIn blocks datacenter
  IPs and requires your logged-in session, so this can't run from a sandbox/CI.
- **Automated LinkedIn access violates LinkedIn's ToS and can get an account
  restricted.** Use a **throwaway account**, keep `max_pages` low, and don't
  hammer it. You accept that risk by using this.
- Job/post fields (title, company, …) are **best-effort** — the MCP returns raw
  page text for an LLM to read, so parsing is heuristic. Every result always
  includes a working LinkedIn link so you can click through.

---

## Setup

**1. One-time LinkedIn MCP setup** (the agent-reach stack):

```bash
# install uv/uvx: https://docs.astral.sh/uv/getting-started/installation/
uvx mcp-server-linkedin@latest --login          # saves your session

mcporter config add linkedin --command uvx \
  --arg mcp-server-linkedin@latest --env UV_HTTP_TIMEOUT=300 --scope home
```

Verify it:

```bash
python -m li_reach check
```

**2. This tool:**

```bash
pip install -r requirements.txt        # just PyYAML
cp config.example.yaml config.yaml     # then edit config.yaml
```

---

## Usage

```bash
python -m li_reach                 # run with ./config.yaml
python -m li_reach --config me.yaml
python -m li_reach --dry-run       # print the mcporter commands, fetch nothing
python -m li_reach --only jobs     # jobs | posts | both (default both)
python -m li_reach --only posts
python -m li_reach -o results/     # override output dir
python -m li_reach check           # verify mcporter + uvx are set up
```

Results land in `out/` (`results.md`, `results.json`, `jobs.csv`).

**Tip:** run `--dry-run` first — it shows the exact LinkedIn queries your spec
produces, with zero risk to your account.

---

## Writing your spec

Everything lives in `config.yaml` (see `config.example.yaml` for the full,
commented template). Your criteria are split into two kinds:

**Native filters** — applied by LinkedIn server-side (accurate, cheap):

| Your spec (`filters:`) | LinkedIn values |
|---|---|
| `date_posted` | `past_hour`, `past_24_hours`, `past_week`, `past_month` |
| `experience_level` | `internship`, `entry`, `associate`, `mid_senior`, `director`, `executive` |
| `job_type` | `full_time`, `part_time`, `contract`, `temporary`, `internship`, … |
| `work_type` | `on_site`, `remote`, `hybrid` |
| `easy_apply` | `true` / `false` |
| `sort_by` | `date`, `relevance` |
| `max_pages` | `1`–`10` |

**Post-filters** — applied to the fetched text (your fine-grained rules):

- `include_keywords` — keep only jobs mentioning at least one
- `exclude_keywords` — drop jobs mentioning any
- `exclude_companies` — drop these companies
- `ranking` — weights for keyword hits, title matches, and recency

"We're hiring" feed posts are configured under `hiring_posts:` — each of your
role keywords is combined with each hiring phrase (e.g. `python backend` +
`we're hiring`) and searched via `search_posts`.

### Enrichment

A bare `search_jobs` returns only job **ids** + a page blob. To show
titles/companies and to make `include/exclude_keywords` actually apply per job,
`li-reach` fetches details for the top `enrichment.top` jobs via
`get_job_details` (one page each — keep it modest). With enrichment off,
un-enriched jobs are **kept** (never silently dropped) and reported as
`(not enriched)`.

---

## Development

```bash
python -m unittest discover -s tests -v
```

The whole pipeline is tested offline with a `MockBackend` (no network, no
login), covering config validation, command building, result normalisation
(JSON / MCP-envelope / noisy text), filtering, ranking, de-dup, and reporting.

### Layout

```
li_reach/
  config.py     # parse + validate config.yaml -> Config
  backend.py    # mcporter invocation + tolerant result normalisation
  parse.py      # best-effort field extraction from raw innerText
  pipeline.py   # search -> enrich -> filter -> rank (jobs & posts)
  report.py     # markdown / json / csv output
  cli.py        # `python -m li_reach`
tests/          # offline unittest suite
```

---

## License

MIT (matching agent-reach). This project is not affiliated with LinkedIn or
with the agent-reach / mcp-server-linkedin authors.
