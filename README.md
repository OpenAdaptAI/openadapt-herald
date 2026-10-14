# herald

> [!IMPORTANT]
> **Status: Internal tooling — not the product.** Herald is release-announcement
> automation used by the OpenAdapt team. It is not part of the OpenAdapt product
> and is not required by any OpenAdapt package.
>
> The OpenAdapt product is the demonstration compiler,
> [`openadapt-flow`](https://github.com/OpenAdaptAI/openadapt-flow), installed
> via the [`OpenAdapt`](https://github.com/OpenAdaptAI/OpenAdapt) launcher
> (`pip install openadapt`): it compiles a demonstrated GUI workflow into a
> deterministic, locally executable program. Healthy runs make no model calls,
> and it halts instead of guessing when verification fails. Lifecycle labels for
> every repository are in the
> [repository lifecycle registry](https://github.com/OpenAdaptAI/.github/blob/main/REPOSITORY_LIFECYCLE.md).

LLM-powered social media announcements from your git history.

Herald collects commits, releases, and merged PRs from your repos, runs them through an LLM with a human-writing-guide-aware prompt, and posts the result to Discord, Twitter/X, and LinkedIn.

## Quick start

```bash
# Install
pip install herald-announce

# Configure (or set env vars)
cp .env.example .env
# Edit .env with your API keys

# Preview what would be posted
herald preview --repos owner/repo --days 7

# Actually post to configured platforms
herald publish --repos owner/repo --content-type release
```

## How it works

```
Collect          Compose           Publish
git log    ──►   LLM generates  ──►  Discord webhook
gh releases      platform-specific    Twitter API
gh pr list       content with         LinkedIn API
                 writing guide        (extensible)
```

1. **Collect** gathers artifacts from git history and GitHub API (commits, releases, merged PRs)
2. **Compose** feeds artifacts to an LLM with a writing guide that avoids AI-sounding language (no "delve," no "leverage," varied sentence length, contractions)
3. **Publish** posts platform-specific content to Discord (via webhook), Twitter/X (via API v2), and LinkedIn (via UGC Posts API)

## Content types

- `release` — Announce a specific release. Best triggered on GitHub Release events.
- `digest` — Weekly roundup across repos. Best on a cron schedule.
- `spotlight` — Deep dive on a single feature. Best triggered manually.

## CLI commands

```bash
herald collect   # Gather and display artifacts
herald compose   # Generate content (no posting)
herald preview   # Alias for compose
herald publish   # Full pipeline: collect → compose → post
herald post      # Post an approved file exactly as written (no model call)
```

## Post an approved file exactly as written

`herald post` is for text a person has already reviewed. It doesn't call a
model, and it never shortens or rewrites the text. If the text is too long,
it refuses and tells you by how much.

```bash
herald post --file approved.txt --platform x \
  --ledger post-ledger.jsonl \
  --expect-sha256 <approved content_sha256> \
  --precheck-timeline
```

What it checks before it sends anything:

- The SHA-256 of the text matches `--expect-sha256`, so an edit after
  approval stops the post. Herald hashes the file's text without its
  trailing newlines. To get that hash, run
  `herald post --file approved.txt --dry-run --json` and copy
  `content_sha256`.
- The text fits X's 280 weighted characters. X counts every link as 23
  characters and most CJK characters and emoji as 2. Herald counts the same
  way and leans long when it can't tell whether X will treat a word as a link.
  A link written without `https://` counts as 23 or its full length,
  whichever is longer. If X still refuses the text as too long, the result
  is `not_sent`.
- The ledger has no record that this exact text was already posted.

Each run reports one of three results, with its own exit code. The result
tells you whether the post exists on X, even when this run sent nothing.

| Result | Exit code | What it means |
|---|---|---|
| `published` | 0 | The post is on X. X returned its id, or Herald found it on the account. It's in the ledger. |
| `not_sent` | 3 | Herald didn't post. The request never left this machine, X refused it, or a check of recent posts found no match after an earlier `uncertain` attempt (`"reconciled": true` in the JSON). |
| `uncertain` | 4 | A request may have reached X, and Herald can't tell yet whether a post exists. |

Herald also reports `uncertain` when it can't read the ledger, or can't open
the X account after an earlier `uncertain` attempt. In both cases this run
sent nothing, but Herald can't rule out an earlier post.

After an `uncertain` result, Herald doesn't retry on its own. The next run
reads the account's 20 most recent posts first. If the text is there, the
ledger records it as published and nothing is sent. If it isn't there yet
and the attempt was less than 2 minutes ago, the result stays `uncertain`
and you run again later. After that, Herald records the check and asks you
to run again with `--retry`. A `--retry` run reads the recent posts once more
before it sends.

The ledger is an append-only JSON Lines file keyed by the SHA-256 of the
text. Herald writes an `uncertain` record before each request, so a crash or
a cancelled job also leaves a record that the next run checks. Keep the
ledger somewhere that outlasts the job, and run one `herald post` at a time
per ledger, because two runs at once can both send. With
`--precheck-timeline`, Herald also skips the post if the text is among the
account's 20 most recent posts. Set the ledger path with `--ledger` or
`HERALD_POST_LEDGER` (environment or `.env`).

`--dry-run` runs the local checks (hash, length, ledger) and never opens the
X account. `HERALD_DRY_RUN=true` has the same effect. A dry run reads the
ledger, so a dry run after an `uncertain` attempt also reports `uncertain`.

LinkedIn stays manual. LinkedIn's
[API Terms of Use](https://www.linkedin.com/legal/l/api-terms-of-use)
(section 3.1) don't allow using its APIs to automate posting, so
`herald post --platform linkedin` exits with `not_sent` and asks you to paste
the text into LinkedIn yourself.

Reading recent posts and creating a post are paid X API calls on
pay-per-use plans. Check the current prices in the X developer console.

## Configuration

All settings are configurable via environment variables with `HERALD_` prefix:

| Variable | Description |
|----------|-------------|
| `HERALD_ANTHROPIC_API_KEY` | Anthropic API key for content generation |
| `HERALD_DISCORD_WEBHOOK_URL` | Discord webhook URL |
| `HERALD_TWITTER_CONSUMER_KEY` | Twitter API consumer key |
| `HERALD_TWITTER_CONSUMER_SECRET` | Twitter API consumer secret |
| `HERALD_TWITTER_ACCESS_TOKEN` | Twitter API access token |
| `HERALD_TWITTER_ACCESS_TOKEN_SECRET` | Twitter API access token secret |
| `HERALD_LINKEDIN_ACCESS_TOKEN` | LinkedIn OAuth2 access token (`w_member_social` scope) |
| `HERALD_GITHUB_TOKEN` | GitHub token for API access |
| `HERALD_REPOS` | Comma-separated repos (`owner/repo` or local paths) |
| `HERALD_DEFAULT_MODEL` | LLM model (default: `claude-sonnet-4-20250514`) |
| `HERALD_LOOKBACK_DAYS` | Default lookback period (default: 7) |
| `HERALD_DRY_RUN` | Set to `true` for preview-only mode |
| `HERALD_POST_LEDGER` | Ledger file for `herald post` (required for a live verbatim post) |

## LinkedIn setup

To post to LinkedIn, you need an OAuth2 access token with the `w_member_social` scope:

1. Create an app at [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps)
2. Under **Products**, request access to **Share on LinkedIn** (grants `w_member_social`)
3. Generate an OAuth2 access token using the 3-legged OAuth flow or the Developer Portal token generator
4. Set `HERALD_LINKEDIN_ACCESS_TOKEN` in your `.env` file

Note: LinkedIn access tokens typically expire after 60 days. For long-lived automation, implement a token refresh flow or use a long-lived token from a LinkedIn app with appropriate permissions.

## GitHub Actions

See `.github/workflows/release-announce.yml` for a ready-to-use workflow that:
- Posts release announcements when a GitHub Release is published
- Posts weekly digests every Monday
- Supports manual triggers with content type selection

## Multi-model quality (optional)

Herald can use [consilium](https://github.com/OpenAdaptAI/openadapt-consilium) for multi-model consensus on important posts:

```bash
pip install herald-announce[consilium]
herald publish --use-consilium --repos owner/repo
```

This queries multiple LLMs, has them cross-review each other's drafts, and synthesizes the best version.

## Writing guide

Herald embeds a writing guide that steers the LLM away from AI-sounding patterns:
- Bans 60+ overused AI words ("delve," "landscape," "leverage")
- Enforces varied sentence length and contractions
- Avoids mechanical transitions and rule-of-three patterns
- Encourages concrete specifics over vague generalities

The guide is based on AI detection research from PNAS, ACL, and Wikipedia's "Signs of AI Writing."

## Development

```bash
git clone https://github.com/OpenAdaptAI/openadapt-herald.git
cd openadapt-herald
uv sync --extra dev
uv run pytest -v
uv run ruff check .
```

## License

MIT
