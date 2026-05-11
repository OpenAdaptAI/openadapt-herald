# Herald + Microsoft Azure DevOps (ADO): Design Options

Status: Draft for review
Owner: richard.abrich@mldsai.com
Related: [README.md](README.md), [DESIGN-APPROVAL-BOT.md](DESIGN-APPROVAL-BOT.md)

## 1. Problem statement

Herald today pulls artifacts from GitHub (`gh` CLI / REST) and local git, then posts
to Discord, Twitter/X, and LinkedIn. Enterprise teams that run on Microsoft Azure
DevOps (ADO) + Microsoft Teams are currently unreachable on both sides:

- We cannot **collect** commits / PRs / work items from ADO-hosted repos.
- We cannot **publish** announcements to Teams channels or ADO surfaces
  (Wiki, work-item comments, Boards).

This doc inventories the integration options, their tradeoffs, and a
recommendation for a minimal-viable first cut.

## 2. How herald is shaped today (ground truth)

Reading the current code:

- `herald/collector.py:230` — `collect_all(repos, ...)` iterates a list of
  `owner/repo` strings (or local paths) and produces `Artifacts` bundles made
  of `Commit`, `Release`, `PullRequest` dataclasses. GitHub is reached via the
  `gh` CLI (`gh api`, `gh pr list`). There is **no** pluggable "source" abstraction;
  GitHub is hard-wired.
- `herald/platforms/base.py:17` — `Publisher` is a clean abstract base with
  `publish()` / `is_configured()` / `platform_name`. Discord, Twitter, LinkedIn
  all subclass it. Adding a new destination is a small, well-bounded change.
- `herald/publisher.py:33` — `get_publishers(settings)` wires concrete
  publishers from config. Straightforward to extend.
- `herald/config.py:11` — `HeraldSettings` is a pydantic-settings model with
  `HERALD_` env prefix. Any new integration adds fields here.
- `herald/composer.py:72` — LLM-facing; platform-agnostic. Reads `content_type`
  and writes a dict keyed by platform name. New destinations just need a new
  key in the returned dict (or a fallback to `summary`).

**Takeaway:** the *publisher* side is already pluggable. The *collector* side
is GitHub-only and will need a small refactor to host a second backend.

## 3. What "ADO support" can mean

ADO is a product suite, not a single surface. There are two orthogonal
integration axes:

| Axis | GitHub analogue today | ADO equivalent(s) |
|------|----------------------|-------------------|
| **Source** (artifacts in) | `gh api`, local git | Azure Repos, Azure Boards, Azure Pipelines |
| **Destination** (posts out) | Discord / Twitter / LinkedIn webhook+API | Microsoft Teams, ADO Wiki, Work Item comments, Dashboards |

These are independent. A team might host code on GitHub but want posts in
Teams, or vice-versa. We should not bundle them.

## 4. ADO primer (what we're integrating with)

### 4.1 Services

- **Azure Repos** — Git (and legacy TFVC). Same mental model as GitHub repos +
  PRs, different field names.
- **Azure Boards** — Work items: Epic / Feature / User Story / Task / Bug.
  Queryable via WIQL (SQL-like). Richer than GitHub Issues in large orgs.
- **Azure Pipelines** — YAML-based CI and the legacy "Classic Release" pipelines.
  Runs are addressable; tags in Repos do not carry release-note bodies the way
  GitHub Releases do.
- **Azure Artifacts** — Package feeds (NuGet/npm/Maven/PyPI). Out of scope.
- **Azure Test Plans** — Out of scope.

### 4.2 URL / identity hierarchy

GitHub: `owner/repo` (2 segments). ADO: `organization/project/repo` (3 segments),
base URL `https://dev.azure.com/{org}/{project}`. Repos inside a project are
identified by name or GUID. This breaks the current `HERALD_REPOS`
comma-separated `owner/repo` shape — see §7.

### 4.3 Auth

Four options, ordered by complexity:

1. **Personal Access Token (PAT)** — HTTP Basic with empty username and the
   PAT as password (`Authorization: Basic base64(":<PAT>")`). Scopes are
   granular (`vso.code`, `vso.work`, `vso.wiki_write`, etc.). Max lifetime is
   one year. Simplest; what `git` uses out of the box.
2. **OAuth 2.0 (ADO-native)** — 3-legged user flow. Deprecated for new apps in
   favor of Entra; still works.
3. **Microsoft Entra ID (Azure AD) token** — Bearer token via
   `az account get-access-token --resource 499b84ac-1321-427f-aa17-267ca6975798`.
   Good for service principals and managed identities. Preferred for enterprise
   automation.
4. **GitHub-style App / "ADO service principal"** — via Entra app registration
   with federated credentials (OIDC from GitHub Actions/Azure Pipelines). Best
   for CI but heavy setup.

PAT is the right default for v1 (parity with current `HERALD_GITHUB_TOKEN`).
Entra is the right default for enterprise v2.

### 4.4 API

- Base: `https://dev.azure.com/{org}/{project}/_apis/...`
- Version: pin `api-version=7.1` (current GA as of this writing).
- Python SDK: `azure-devops` (official, MIT-licensed; wraps REST).
- Key endpoints we'd touch:
  - `GET /_apis/git/repositories/{repo}/commits` — commits.
  - `GET /_apis/git/repositories/{repo}/pullrequests?searchCriteria.status=completed`
    — merged PRs (ADO calls it "completed"; field is `closedDate`).
  - `GET /_apis/git/repositories/{repo}/refs?filter=tags/` — tags (the only
    "release" primitive in Repos).
  - `GET /_apis/pipelines/{id}/runs` — pipeline runs, optional "release" proxy.
  - `POST /_apis/wit/wiql` — work item queries (for Boards).
  - `PUT /_apis/wiki/wikis/{wikiId}/pages?path=/...` — create/update wiki page.
  - `POST /_apis/wit/workItems/{id}/comments?api-version=7.1-preview` — WI comment.

### 4.5 Teams posting is a moving target

This is the single biggest gotcha in the whole design:

- **Incoming Webhooks ("O365 Connectors")** in Teams are being **retired**.
  Microsoft announced deprecation of Office 365 Connectors; creation of new
  connectors was disabled in 2024 and existing connectors stop working on a
  rolling schedule through late 2025. **Do not build v1 on this.**
- **Replacement: "Workflows" (Power Automate)** — user creates a "Post to a
  channel when a webhook request is received" flow; Power Automate mints a URL
  that looks like a webhook. Same ergonomics from our side (HTTP POST
  adaptive-card JSON), different setup.
- **Graph API** — `POST /teams/{team-id}/channels/{channel-id}/messages` with
  an app registration holding `ChannelMessage.Send` (delegated) or
  `Teamwork.Migrate.All` + RSC (application). More powerful, more setup,
  requires tenant admin consent.
- **Bot Framework** — overkill unless we want two-way interaction (cf.
  [DESIGN-APPROVAL-BOT.md](DESIGN-APPROVAL-BOT.md)).

## 5. Options

I'll cover source and destination options separately; pick one of each.

### 5.A Source options (collect from ADO)

#### A1 — `azure-devops` Python SDK

Add a dependency on `azure-devops`, map ADO PR/commit objects to the existing
`Commit` / `PullRequest` dataclasses in `collector.py`.

- **Pros:** typed clients, handles paging and auth; Microsoft-maintained.
- **Cons:** another transitive dependency tree (`msrest`, etc.); SDK lags
  behind REST; test mocking is noisier than raw HTTP.
- **Effort:** ~1 day. Fits cleanly alongside `collect_github_*` functions.

#### A2 — Raw REST via `httpx`

Call ADO REST directly with PAT basic-auth. No SDK.

- **Pros:** zero new deps (if we're OK adding `httpx`; else use `urllib`);
  easy to test with `respx`/recorded fixtures; one source of truth for API
  version pinning.
- **Cons:** we own paging, retry, rate-limit handling; ~200 LOC we didn't
  write before.
- **Effort:** ~1.5 days including tests.

#### A3 — `az` CLI + `az devops` extension (mirrors the current `gh` pattern)

Shell out to `az repos pr list` / `az repos ref list` the way `collector.py`
shells out to `gh`.

- **Pros:** cleanest architectural match with today's code
  (`collector.py:131`, `collector.py:180`); auth inherits from the user's
  `az login`; good for local dev.
- **Cons:** requires `az` + `azure-devops` extension on the runner; slower
  (process spawn per call); enterprise CI runners may not have `az`; output
  schema is less stable than REST.
- **Effort:** ~0.5 day for the happy path, more for CI packaging.

#### A4 — Git-only (local clones, skip the API)

Use the existing `collect_git_commits()` against a local clone of the ADO
repo. No PRs, no work items, no tags-with-bodies.

- **Pros:** zero new code; works today.
- **Cons:** loses the richest signal (PRs and Boards are where narrative
  lives in ADO shops); requires cloning in CI.
- **Effort:** 0. Document, ship.

**Recommendation (source): A2 (raw REST).** Mirrors `collect_github_*` in
shape, avoids SDK churn, makes tests deterministic. A3 looks tempting for
symmetry with `gh` but `az` is a heavyweight CLI to require in CI.

### 5.B Adding Boards to the mix (optional, orthogonal)

ADO shops often have weak release notes but rich completed-work-item streams.
A digest that says "this sprint we closed 14 stories across 3 epics" is often
more valuable than a commit log. Proposal:

- Extend `Artifacts` with `work_items: list[WorkItem]` (Epic/Feature/Story/Bug).
- Add a `collect_ado_workitems(org, project, wiql, since_days)` using the
  WIQL endpoint, filtered by `System.ChangedDate > @Today - N`.
- Feed into the existing `digest` prompt.

This is additive; can ship after A2.

### 5.C Destination options (post to ADO / Teams)

#### C1 — Teams via Power Automate Workflow webhook (replacement for Connectors)

User creates the Workflow once, gets a webhook URL, we POST an adaptive-card
payload to it.

- **Pros:** simplest possible UX, near-identical to `DiscordPublisher`
  (`herald/platforms/discord.py:8`); no app registration; no admin consent.
- **Cons:** per-channel setup is manual and tribal knowledge; adaptive-card
  schema is more verbose than Discord's JSON; Microsoft changes the story
  every ~18 months.
- **Effort:** ~0.5 day. **Maps onto existing `DiscordPublisher` pattern 1:1.**

#### C2 — Teams via Microsoft Graph API

App registration with `ChannelMessage.Send.Group` (RSC) or delegated
permissions; call `POST /teams/{id}/channels/{id}/messages`.

- **Pros:** tenant-wide, programmatic discovery of channels, richer features
  (mentions, threading, edit/delete). Correct choice for a product.
- **Cons:** requires Entra app registration + admin consent; RSC requires the
  app to be installed in each team; local dev needs device-code flow.
  Significant documentation burden on users.
- **Effort:** ~3–5 days including setup docs and token-refresh.

#### C3 — Teams via legacy Incoming Webhook (Connector)

Same shape as Discord. **Deprecated; do not build.** Mentioned only so we
explicitly reject it.

#### C4 — ADO Wiki page

On release, `PUT` a markdown page under `/releases/YYYY-MM-DD-{tag}` in a
project wiki.

- **Pros:** durable, searchable, lives next to the code; great for audit /
  compliance orgs.
- **Cons:** not a notification channel — nobody reads it live. Only valuable
  paired with another destination.
- **Effort:** ~1 day.

#### C5 — ADO Work Item comment

Post an announcement as a comment on the tracking Epic / Feature for the release.

- **Pros:** keeps the announcement attached to the governance artifact.
- **Cons:** requires the caller to know the right work-item ID; not a
  broadcast mechanism.
- **Effort:** ~0.5 day. Nice as a secondary destination.

**Recommendation (destination): C1 for v1, plan for C2 in v2.** C1 ships this
week and gives the Discord-equivalent experience; C2 is the right long-term
answer but the setup cost is too high to gate the first release on.

## 6. Recommended v1

Scope:

1. **New collector:** `herald/collector_ado.py` exposing
   `collect_ado(org, project, repos, since_days, pat)` that returns the
   existing `Artifacts` shape. Raw REST via `httpx`. Tags treated as releases
   (body synthesized from commit range). PRs mapped from `pullrequests?status=completed`.
2. **New publisher:** `herald/platforms/teams.py` with `TeamsPublisher` taking
   a Power Automate workflow URL, posting adaptive cards. Mirrors
   `DiscordPublisher`.
3. **Config additions in `herald/config.py`:**
   - `ado_pat: str`
   - `ado_org: str`
   - `ado_project: str`
   - `ado_repos: str` (comma-separated)
   - `teams_webhook_url: str`
   - `has_ado` / `has_teams` properties
   - `repo_list` stays GitHub-flavoured; add parallel `ado_repo_list`.
4. **Collector dispatch:** in `collect_all()` (`collector.py:230`), if
   `settings.has_ado` is set, also call `collect_ado(...)` and merge.
   Alternative: a thin `Source` protocol — not required for v1 but cheap.
5. **Composer:** add `"teams"` to the platform keys the prompts emit.
   Writing guide applies unchanged. Fall back to `summary` otherwise.
6. **Docs:** a README section mirroring "LinkedIn setup", explaining PAT
   scopes (`vso.code`, `vso.work`) and the Power Automate Workflow recipe
   (screenshots out of scope).

Explicitly **out of scope for v1:** Boards / WIQL, Graph API, Wiki posting,
work-item comments, OAuth, Entra auth. Each has a ticket shape in §8.

## 7. Risks and open questions

- **Repo identifier format.** `HERALD_REPOS` is today a flat comma-list of
  `owner/repo`. Simplest ADO extension is a separate `HERALD_ADO_REPOS`
  (names scoped to a single org/project). Multi-project is a later fight.
  **Decision needed before coding.**
- **"Release" semantics in ADO.** No native release body. Options: (a) use
  last tag + commit-range body, (b) require teams to put a `CHANGELOG.md` in
  the repo root and diff it, (c) parse Azure Pipelines run metadata. (a) is
  the cheapest v1.
- **Teams Workflow longevity.** Microsoft has deprecated O365 Connectors,
  and Workflows is the official replacement, but the Workflows path is
  younger — we should expect at least one API break. Mitigation: keep
  `TeamsPublisher` thin, isolate the payload schema.
- **PAT rotation.** 1-year max. Same class of problem as LinkedIn's 60-day
  token (see README §LinkedIn setup). Document, don't solve yet.
- **Rate limits.** ADO uses Throughput Units (TSTUs) rather than simple
  req/min. Unlikely to bite herald's traffic pattern but worth a comment in
  the REST client.
- **Private-by-default.** ADO content is frequently customer-confidential.
  Herald already posts to public surfaces. We should surface a `--allow-public`
  style flag, or at minimum loud warnings, when a publisher for a public
  platform is enabled alongside an ADO source. Ties into the
  `NEVER mention enterprise customer names` rule.

## 8. Follow-up tickets (not in v1)

- ADO Boards source (WIQL) → feeds `digest`.
- Graph API Teams publisher (replacing C1 for product use).
- ADO Wiki publisher (C4).
- Work-item comment publisher (C5).
- Entra ID / managed-identity auth.
- Service-hook receiver (ADO → herald trigger, inverse direction).
- Secret-scrubbing pass for ADO sources (reuse `openadapt-privacy`).

## 9. TL;DR

- Publisher abstraction is already clean; adding Teams is a ~1-file change.
- Collector is GitHub-hardcoded; adding ADO means a sibling `collector_ado.py`
  and a merge point in `collect_all`.
- Build v1 on **raw REST + PAT** (source) and **Power Automate Workflow
  webhook** (destination). Skip the deprecated O365 Connector and defer Graph
  API until there's a second customer asking for it.
