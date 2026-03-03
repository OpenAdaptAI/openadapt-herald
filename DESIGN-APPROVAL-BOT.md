# Crier: Event-Driven Social Media Bot with Telegram Approval

## Problem

Herald generates social media content on demand (CLI/cron), but there's no
mechanism for:
- Real-time response to commits/releases
- Human review before posting
- Edit/reject workflows
- Conversational feedback on drafts

We need a system that watches repos, drafts content, and asks for approval via
Telegram before publishing.

---

## Options Considered

### Option A: New standalone project ("crier")

A focused Python project that watches GitHub events, generates drafts via
herald, and manages approval via a Telegram bot.

```
consilium   →  multi-model consensus (library)
herald      →  content generation + publishing (CLI)
crier       →  event-driven approval bot (daemon)
```

**Pros:**
- Clean separation: herald = content generation, crier = event loop + approval UX
- Follows established pattern of small, focused tools
- Independently useful — anyone could use crier with different content generators
- Herald stays a simple CLI tool; crier is the always-on daemon
- Different deployment model is explicit (CLI/cron vs long-running process)

**Cons:**
- Third project to maintain
- Some wiring needed between crier and herald

### Option B: Extend herald with a "bot" mode

Add `herald bot` command that runs an always-on Telegram approval daemon.

**Pros:**
- Single project, shared config/deps
- Herald already has composer + publisher

**Cons:**
- Herald becomes less focused (content gen + event listener + Telegram bot)
- Muddies the CLI-tool identity
- Harder for others to use one capability without the other
- Different deployment model awkwardly coexists (cron + daemon)
- Adds python-telegram-bot, aiosqlite to herald's required deps

### Option C: n8n workflow

Use n8n's "GPT-4 + Telegram Approval" template with a GitHub webhook trigger.

**Pros:**
- Near-zero code; visual workflow editor
- Template exists for this exact pattern
- Self-hosted, open source

**Cons:**
- Another system to run and maintain (n8n server + database)
- Limited customization (no writing guide, no consilium, no custom prompts)
- Not version-controlled code; opaque workflow JSON
- Can't reuse herald's composer/publisher
- JavaScript/TypeScript runtime, not Python

### Option D: OpenClaw

Use OpenClaw as the AI agent backbone with a Mixpost skill for social media.

**Pros:**
- 243k GitHub stars, very active, Telegram built-in
- MCP server support, extensible skills
- Could be powerful long-term

**Cons:**
- TypeScript/Node.js — different language from entire stack
- Massive scope (personal AI assistant, not a social media tool)
- "Security nightmare" per Cisco's analysis
- Would need custom skills for our workflow
- Overkill: we need a focused bot, not a general-purpose AI assistant
- Creator joined OpenAI; future governance unclear

### Option E: Use Typefully/Buffer API

Post drafts to Typefully (which has its own approval UI), triggered by GitHub Actions.

**Pros:**
- Professional scheduling/approval UI
- Multi-platform publishing built in
- GitHub Action exists (riccardolinares/typefully)

**Cons:**
- Third-party dependency (Typefully could change pricing/API)
- No custom LLM prompts or writing guide
- Monthly cost ($12+/month for useful features)
- Approval happens in Typefully's web UI, not in Telegram
- Can't integrate consilium

---

## Recommendation: Option A — New project "crier"

Create `crier` as a standalone project that:
1. Follows the consilium/herald pattern (small, focused, reusable)
2. Uses herald as a library dependency for compose/publish
3. Owns the event-listening and Telegram approval UX
4. Stays in the same monorepo (`openadapt-crier/`)

This is the right boundary because:
- Herald's job is "turn artifacts into social media posts" — it does this well
- Crier's job is "watch for events, get human approval, trigger herald" — different concern
- A daemon process has fundamentally different lifecycle than a CLI tool
- Keeps both tools useful independently

---

## Architecture

```
┌──────────────────────────────────────────────┐
│                    Crier                      │
│                                              │
│  ┌──────────┐    ┌──────────┐    ┌────────┐  │
│  │ Event    │───→│ Draft    │───→│Telegram│  │
│  │ Watcher  │    │Generator │    │Approval│  │
│  └──────────┘    └──────────┘    └───┬────┘  │
│       │                              │       │
│       │          ┌──────────┐        │       │
│       │          │ SQLite   │←───────┘       │
│       │          │ State    │                │
│       │          └──────────┘                │
│       │                              │       │
│       │          ┌──────────┐        │       │
│       └─────────→│ Post     │←───────┘       │
│                  │Dispatcher│                │
│                  └──────────┘                │
│                       │                      │
│              ┌────────┼────────┐             │
│              │        │        │             │
│              v        v        v             │
│          Twitter  Discord  LinkedIn          │
│                                              │
│  Uses: herald (compose/publish)              │
│        consilium (optional, via herald)      │
│        python-telegram-bot (approval UX)     │
└──────────────────────────────────────────────┘
```

### Components

#### 1. Event Watcher

Detects new commits/releases/PRs. Two modes:

**Poll mode** (default, simpler):
- Runs on a configurable interval (default: 60s)
- Uses `gh api` or GitHub REST API to check for new commits
- Tracks last-seen commit SHA per repo in SQLite
- No public URL needed, works behind NAT

**Webhook mode** (optional, for lower latency):
- Embedded FastAPI server receives GitHub webhook POSTs
- Verifies `X-Hub-Signature-256` with HMAC
- Requires a public URL (Fly.io, ngrok, etc.)

**Recommendation:** Start with poll mode. 60s latency is fine for social media.
Switch to webhooks later if needed.

#### 2. Draft Generator

When new events are detected:

1. Collect artifacts using `herald.collector.collect_all()`
2. Determine content type based on event:
   - Push to main with multiple commits → `digest`
   - GitHub release published → `release`
   - Notable PR merged → `spotlight`
   - Single interesting commit → custom short-form prompt
3. Compose content using `herald.composer.compose()`
4. Store draft in SQLite with status `pending`

**Smart filtering** — not every commit deserves a tweet:
- Skip merge commits, dependency bumps, CI-only changes
- Use LLM to score "interestingness" (0-10) before drafting
- Configurable threshold (default: 5)
- Always draft for releases and tagged commits

#### 3. Telegram Approval Bot

The human-in-the-loop interface:

```
┌──────────────────────────────────────────┐
│ 🔔 New commit on OpenAdaptAI/OpenAdapt   │
│                                          │
│ abc1234 by @author                       │
│ "Fix login flow OAuth callback bug"      │
│                                          │
│ ── Draft (Twitter) ──────────────────    │
│ Just shipped a fix for the OAuth         │
│ callback in the login flow. The 500      │
│ errors on redirect are gone.             │
│                                          │
│ ── Draft (Discord) ──────────────────    │
│ **Bug Fix: OAuth Login Flow**            │
│ Fixed the 500 error that occurred...     │
│                                          │
│ [✓ Approve] [✎ Edit] [✗ Reject]         │
└──────────────────────────────────────────┘
```

**Flows:**

- **Approve** → bot posts to all platforms, edits message to show "Posted" with URLs
- **Edit** → bot asks "Send me the revised text" → user types new text →
  bot shows updated draft with new Approve/Edit/Reject buttons
- **Reject** → bot marks as rejected, edits message to show "Rejected",
  optionally asks for reason (for LLM feedback loop)

**Platform selection buttons** (second row):
```
[Twitter ✓] [Discord ✓] [LinkedIn ✓]
```
Toggle which platforms to post to before approving.

**Implementation:**
- `python-telegram-bot` v22 (28k stars, 42.5M monthly downloads)
- Inline keyboards for approve/edit/reject
- `callback_data` encodes draft ID + action
- Long-polling mode (no public URL needed)
- Conversation handler for edit flow

#### 4. SQLite State Store

```sql
CREATE TABLE events (
    id TEXT PRIMARY KEY,         -- UUID
    repo TEXT NOT NULL,
    event_type TEXT NOT NULL,    -- push, release, pr_merged
    ref TEXT,                    -- commit SHA, tag, PR number
    payload TEXT,                -- JSON of event data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE drafts (
    id TEXT PRIMARY KEY,         -- UUID
    event_id TEXT REFERENCES events(id),
    platform TEXT NOT NULL,      -- twitter, discord, linkedin
    content TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    -- pending → approved → posted
    -- pending → rejected
    -- pending → edited → pending (re-enters approval)
    telegram_message_id INTEGER,
    telegram_chat_id INTEGER,
    interestingness_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    posted_at TIMESTAMP,
    post_url TEXT,
    error TEXT
);

CREATE TABLE feedback (
    id TEXT PRIMARY KEY,
    draft_id TEXT REFERENCES drafts(id),
    action TEXT NOT NULL,        -- approve, reject, edit
    user_text TEXT,              -- edit text or reject reason
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 5. Post Dispatcher

On approval:
1. Read draft content from SQLite
2. Call `herald.publisher.publish_content()` for selected platforms
3. Update SQLite with post URLs and status
4. Edit Telegram message to show results

---

## Technology Choices

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.10+ | Same as consilium/herald, shared ecosystem |
| Telegram | python-telegram-bot v22 | 28k stars, best docs, inline keyboards |
| Event source | GitHub REST API polling | No public URL needed, simple, sufficient latency |
| State | SQLite (aiosqlite) | Zero deps, durable, queryable, crash-safe |
| Scheduling | APScheduler | In-process cron for polling intervals |
| Content gen | herald (dependency) | Reuse composer + publisher + writing guide |
| Config | pydantic-settings | Same pattern as herald, CRIER_ prefix |
| CLI | typer | Same as herald, for one-off commands |
| Deployment | systemd or Fly.io | Always-on process, free tier sufficient |

### Why python-telegram-bot over aiogram?

Both are capable. python-telegram-bot wins here because:
- 5x more GitHub stars (28k vs 5.5k)
- 200x more PyPI downloads (42.5M vs 870k monthly)
- More English documentation and examples
- Simpler API for our use case (we don't need aiogram's FSM/middleware/router complexity)
- Our "state machine" is trivial (pending → approved/rejected)

### Why polling over webhooks?

- No public URL needed (works from laptop, CI, anywhere)
- GitHub API rate limit is 5,000/hour; polling 3 repos every 60s = 180 requests/hour (3.6%)
- 60s latency is irrelevant for social media
- Can always add webhooks later as an alternative mode

### Why SQLite over Redis?

- Zero infrastructure (single file)
- Crash-safe by default (WAL mode)
- Full SQL for querying history ("show me all approved tweets this month")
- Sufficient throughput (a few events/day)
- Persists through restarts without configuration

---

## Configuration

```env
# Crier configuration
# Copy to .env and fill in your values.

# Telegram bot token (from @BotFather)
CRIER_TELEGRAM_BOT_TOKEN=123456:ABC-DEF...

# Your Telegram user ID (for DM authorization)
CRIER_TELEGRAM_OWNER_ID=123456789

# Repos to watch (comma-separated owner/repo)
CRIER_REPOS=OpenAdaptAI/OpenAdapt,OpenAdaptAI/openadapt-evals

# GitHub token (for API polling)
CRIER_GITHUB_TOKEN=ghp_...

# Poll interval in seconds (default: 60)
CRIER_POLL_INTERVAL=60

# Interestingness threshold (0-10, default: 5)
CRIER_INTEREST_THRESHOLD=5

# Herald settings (inherited or overridden)
CRIER_ANTHROPIC_API_KEY=sk-ant-...
CRIER_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
CRIER_TWITTER_CONSUMER_KEY=...
CRIER_TWITTER_CONSUMER_SECRET=...
CRIER_TWITTER_ACCESS_TOKEN=...
CRIER_TWITTER_ACCESS_TOKEN_SECRET=...

# Database path (default: ./crier.db)
CRIER_DB_PATH=./crier.db
```

---

## CLI Interface

```bash
# Start the bot (main mode — runs forever)
crier run

# Start with webhook mode instead of polling
crier run --webhook --port 8080

# Check status
crier status

# List recent drafts
crier drafts --status pending
crier drafts --status posted --days 7

# Manually trigger a draft for a repo
crier draft OpenAdaptAI/OpenAdapt --content-type digest --days 7

# Show posting history
crier history --platform twitter --days 30
```

---

## Project Structure

```
crier/
├── pyproject.toml
├── .env.example
├── crier/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py              # typer CLI
│   ├── config.py            # pydantic-settings, CRIER_ prefix
│   ├── bot.py               # Telegram bot (inline keyboards, callbacks)
│   ├── watcher.py           # GitHub event polling + webhook receiver
│   ├── drafter.py           # LLM interestingness scoring + draft generation
│   ├── dispatcher.py        # Post to platforms via herald
│   ├── db.py                # SQLite schema + queries (aiosqlite)
│   └── filters.py           # Commit filtering (skip merges, deps, CI)
└── tests/
    ├── test_bot.py
    ├── test_watcher.py
    ├── test_drafter.py
    ├── test_dispatcher.py
    ├── test_db.py
    └── test_filters.py
```

---

## Event Flow (Detailed)

```
1. Watcher polls GitHub API every 60s
   └─ GET /repos/{owner}/{repo}/commits?since={last_check}
   └─ Compare with last-seen SHA in SQLite
   └─ If new commits found:

2. Filter commits
   └─ Skip: merge commits, dependabot, [ci skip], version bumps
   └─ Group: if 5+ commits since last check, treat as batch → digest
   └─ Single notable commit → individual draft

3. Score interestingness (LLM)
   └─ Quick Claude call: "Rate 0-10 how interesting this is for social media"
   └─ Input: commit message, diff stats, file list
   └─ If score < threshold → skip, log, continue
   └─ If score >= threshold → proceed to draft

4. Generate draft (via herald)
   └─ herald.collector.Artifacts from the new commits
   └─ herald.composer.compose() with appropriate content_type
   └─ Returns dict: {twitter: "...", discord: "...", linkedin: "..."}
   └─ Store all platform drafts in SQLite

5. Send to Telegram
   └─ Format message with commit info + all platform drafts
   └─ Attach inline keyboard: [✓ Approve] [✎ Edit] [✗ Reject]
   └─ Second row: [Twitter ✓] [Discord ✓] [LinkedIn ✓]
   └─ Store telegram_message_id in SQLite

6. Await human decision
   └─ Approve → go to step 7
   └─ Edit → bot asks for new text → update draft → show new buttons
   └─ Reject → mark rejected, edit message, done

7. Post via herald
   └─ herald.publisher.publish_content() for selected platforms
   └─ Update SQLite with URLs and status
   └─ Edit Telegram message: "✅ Posted" + URLs

8. Record feedback
   └─ Store action + any user text in feedback table
   └─ Future: use rejection reasons to improve prompts
```

---

## Security

- **Telegram auth**: Only respond to messages from `CRIER_TELEGRAM_OWNER_ID`
- **GitHub webhook verification**: HMAC-SHA256 signature check (webhook mode)
- **No credentials in code**: All secrets via environment variables
- **Private repo**: Crier stays private under `OpenAdaptAI/`
- **SQLite**: Local file, no network exposure
- **Rate limiting**: Track Twitter post count, warn at 400/month, refuse at 480

---

## Hosting: Self-Hosted vs Remote

### The Problem

An always-on Telegram polling bot can't run on a laptop (sleep kills it).
It needs a host that is always up.

### Hosting Options Compared

| Platform | Always-On? | Free? | Monthly Cost | Notes |
|----------|-----------|-------|-------------|-------|
| **Oracle Cloud Always Free** | Yes | Yes, forever | $0 | 4 ARM cores, 24GB RAM. Best free option. Capacity can be hard to get in popular regions. |
| **Fly.io** | Yes | No (7-day trial only, no free tier since late 2024) | ~$2.65/mo | Good DX, Dockerfile deploy, persistent volumes. |
| **Railway** | Yes | 30-day trial | $5/mo min | Simple GitHub deploy. Not free long-term. |
| **Render** | Sleeps after 15min | Yes (with sleep) | $0 / $7 always-on | Free tier not viable for polling bot. |
| **VPS (Hetzner/DO)** | Yes | No | $3.50-5/mo | Full control, systemd, reliable. |
| **Mac (launchd)** | No (laptop sleep) | Yes | $0 | Only viable on a Mac Mini / headless machine that never sleeps. |
| **GitHub Actions** | No | Yes | $0 | Max 6hr runs, unreliable cron. Cannot run always-on bot. |

### Hosting Recommendation

**Primary: Oracle Cloud Always Free** — genuinely $0/month forever, full Linux
VM with systemd, SQLite on local disk. Only downside is getting an instance
(capacity limited in popular regions).

**Fallback: Fly.io at ~$2.65/mo** — if Oracle isn't available. Dockerfile
deploy, persistent volume for SQLite, auto-restarts.

**Dev/testing: Local Mac** — use `caffeinate` or a headless machine for dev.
Not for production.

---

## State Backend: SQLite vs Alternatives

### Options Compared

| Backend | Cost | Infra | Latency | Queryable | Dashboard | Notes |
|---------|------|-------|---------|-----------|-----------|-------|
| **SQLite (local)** | $0 | None | Microseconds | Full SQL | No | Best for VPS/Oracle. On Fly.io persistent volumes: works, daily snapshots. |
| **GitHub Issues (IssueOps)** | $0 | None | 100-500ms | Labels/search | Yes (GitHub UI) | Labels = state, comments = audit trail. Mobile-friendly approval via GitHub app. |
| **Turso (hosted libSQL)** | $0 free tier | Managed | ~10ms | Full SQL | Web console | SQLite-compatible. 500M reads/mo free. Python SDK exists. |
| **Supabase (Postgres)** | $0 free tier | Managed | ~50ms | Full SQL | Dashboard | Free projects pause after 1 week inactivity — dealbreaker for low-traffic bot. |
| **Neon (Postgres)** | $0 free tier | Managed | ~50ms (cold start) | Full SQL | Dashboard | Scale-to-zero. 100 CU-hours/mo free. Overkill for this use case. |
| **Cloudflare D1** | $0 free tier | Edge | ~100ms | Full SQL | Dashboard | Designed for Workers, not standalone Python. Poor fit. |

### GitHub Issues as State Store (IssueOps)

A creative but well-established pattern:

- Each draft → GitHub Issue in the private crier repo
- Labels represent state: `pending`, `approved`, `rejected`, `posted`
- Issue body contains the draft content (multi-platform, YAML front matter)
- Comments track approval conversation and post URLs
- GitHub API for CRUD (5,000 requests/hr, plenty for a few events/day)
- Mobile-friendly: approve posts by adding labels from the GitHub app

**IssueOps is an established pattern** — GitHub themselves use and document it.

**Pros:** Free, zero infra, built-in UI/search/audit trail, works from phone.
**Cons:** No relational queries, 100-500ms API latency, no transactions.

### State Recommendation

**Hybrid: SQLite (operational) + GitHub Issues (approval workflow)**

- **SQLite** for fast bot-internal state: last-seen commit SHAs, rate limit
  counters, Telegram message IDs, post history, metrics
- **GitHub Issues** for the human-facing approval workflow: draft review,
  edit conversation, approval audit trail — gives us a free dashboard

This means the bot can reconstruct its approval state from GitHub Issues on
restart, while keeping fast local state for operational bookkeeping.

Alternatively, **SQLite-only** is perfectly fine and simpler. The GitHub Issues
approach is a nice-to-have, not a requirement.

---

## Deployment Configurations

### Config A: Oracle Cloud + SQLite (Recommended — $0/mo)

```
┌─────────────────────────────────────┐
│  Oracle Cloud ARM VM (free forever) │
│                                     │
│  systemd service: crier             │
│    ├── Telegram polling loop        │
│    ├── GitHub API poller (60s)      │
│    └── SQLite: /var/lib/crier/      │
│              crier.db               │
│                                     │
│  Backup: cron → rclone → S3/GCS    │
└─────────────────────────────────────┘
```

### Config B: Fly.io + SQLite (~$2.65/mo)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install uv && uv sync
CMD ["uv", "run", "crier", "run"]
```

```toml
# fly.toml
app = "crier-bot"
[build]
  dockerfile = "Dockerfile"
[env]
  CRIER_DB_PATH = "/data/crier.db"
[[mounts]]
  source = "crier_data"
  destination = "/data"
```

### Config C: Local Mac (dev only)

```bash
# Keep awake (dev mode)
caffeinate -s uv run crier run
```

Not for production — laptop sleep kills the process.

---

## Dependencies

```toml
[project]
name = "crier"
dependencies = [
    "herald-announce",          # content generation + publishing
    "python-telegram-bot>=22",  # Telegram bot
    "aiosqlite>=0.20",          # async SQLite
    "apscheduler>=3.10",        # in-process scheduling
    "httpx>=0.27",              # async HTTP (GitHub API polling)
    "typer>=0.9",               # CLI
    "pydantic-settings>=2.0",   # config
    "rich>=13.0",               # terminal output
]

[tool.uv.sources]
herald-announce = { path = "../openadapt-herald", editable = true }
```

---

## Relationship to PLAN-generalized-dev-automation.md

The dev automation plan (the generalized dev automation plan)
describes a generalized Ralph Loop worker that generates PRs via Claude Agent SDK.
That plan also includes a Telegram bot for approving dev tasks.

### The full ecosystem

```
consilium        →  multi-model consensus (library)
herald           →  content generation + publishing (CLI/cron)
crier            →  event-driven social media approval bot (daemon)
wright           →  iterative code gen + test + fix loop (worker)
```

### How they connect

```
wright worker
    │ generates PRs on OpenAdapt repos
    v
GitHub (commits, PRs, releases)
    │ detected by
    v
crier (event watcher)
    │ drafts via
    v
herald (compose + publish)
    │ sends to
    v
Telegram (human approves)
    │ posts to
    v
Twitter / Discord / LinkedIn
```

The dev automation worker is an **event source** for crier. As it generates
more PRs, crier has more events to announce.

### Shared Telegram bot?

The dev automation plan (Section 9) suggests sharing one Telegram bot with two
command groups: `/build` for dev tasks, `/post` for social media. This is worth
considering:

**Shared bot (one process, two command groups):**
- Pros: Single bot token, single chat, unified mobile experience
- Cons: Language mismatch (dev worker is TypeScript, crier is Python);
  coupling two independent systems; harder to deploy independently

**Separate bots (recommended for now):**
- Pros: Independent deployment, independent languages, cleaner boundaries
- Cons: Two bot tokens, two chats (or one chat with two bots)
- Can always merge later if the two-bot UX feels clunky

### Decision: Separate bots, same Telegram chat

Both bots DM you in Telegram. You interact with each via its own commands.
If the UX is awkward, merge into a shared bot later. Starting separate is
easier and follows the small-focused-tools pattern.

---

## Order of Operations (Cross-Project)

Based on `INFRASTRUCTURE-FUSION-ANALYSIS.md` priority ratings and dependency
analysis, here is the recommended build order:

### Phase 1 (Now, P0): Dev Automation Worker MVP

_From PLAN-generalized-dev-automation.md, Milestone 1_

1. Create the new monorepo (name TBD)
2. Extract and generalize fastable2 worker code
3. Implement pytest test runner + repo auto-detection
4. Create Supabase project with job queue schema
5. Deploy to Fly.io with scale-to-zero
6. Test: manual Supabase job insert → worker runs → PR created

**Why first:** Highest value (accelerates all development), 80%+ code exists
in fastable2, zero dependency on herald/crier.

### Phase 2 (Parallel, P0): DC Eval Signal

Continue the OpenAdapt eval work (recording real demos on Azure VM). Orthogonal
to dev automation but equally critical for proving OpenAdapt's core thesis.

### Phase 3 (Weeks 3-4): Dev Automation Telegram Bot

_From PLAN-generalized-dev-automation.md, Milestone 2_

1. Build `apps/bot/` in the dev automation repo
2. Commands: `/build`, `/status`, `/cancel`
3. Inline keyboards for PR approval (merge/close/iterate)
4. Job completion notifications

**Why before crier:** Establishes the Telegram inline keyboard approval
pattern that crier will follow. Also makes the dev worker usable from mobile.

### Phase 4 (Weeks 4-5): Herald Weekly Digests Running

Herald's GitHub Actions workflow is already deployed. Verify it's posting
weekly digests to Discord reliably. Fix any issues.

**Why now:** Low effort, validates the content pipeline that crier will reuse.

### Phase 5 (Weeks 5-7): Crier

Build the crier project following this design doc:

1. Create repo at `OpenAdaptAI/crier` (private)
2. Implement watcher, drafter, bot, dispatcher, db
3. Deploy to Oracle Cloud (or Fly.io)
4. Wire to herald for content generation + publishing

**Why after dev automation bot:** The dev worker is now generating PRs, giving
crier real events to announce. The Telegram approval pattern is proven.

### Phase 6 (Weeks 7+): Hardening and Enhancements

- Dev worker: budget guards, circuit breakers, stale job recovery
- Crier: smart scheduling, feedback loop, analytics
- Optional: web dashboard for dev worker (Next.js on Vercel)
- Optional: merge Telegram bots if two-bot UX is awkward

---

## Future Enhancements

1. **Feedback loop**: Use rejection reasons to improve LLM prompts over time
2. **Smart scheduling**: Queue approved posts for optimal posting times
3. **Thread mode**: For Twitter, generate thread drafts from longer content
4. **Image generation**: Auto-generate preview images for tweets
5. **Analytics**: Track engagement metrics, feed back into content strategy
6. **Multi-user**: Support multiple approvers with different permissions
7. **Webhook mode**: Add FastAPI server for GitHub webhooks (lower latency)
8. **Consilium integration**: Use multi-model consensus for higher-stakes posts
9. **GitHub Issues as approval UI**: IssueOps pattern for non-Telegram approval
10. **Shared Telegram bot**: Merge dev automation + crier into one bot if needed
