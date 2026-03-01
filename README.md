# herald

LLM-powered social media announcements from your git history.

Herald collects commits, releases, and merged PRs from your repos, runs them through an LLM with a human-writing-guide-aware prompt, and posts the result to Discord and Twitter/X.

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
gh pr list       content with         (extensible)
                 writing guide
```

1. **Collect** gathers artifacts from git history and GitHub API (commits, releases, merged PRs)
2. **Compose** feeds artifacts to an LLM with a writing guide that avoids AI-sounding language (no "delve," no "leverage," varied sentence length, contractions)
3. **Publish** posts platform-specific content to Discord (via webhook) and Twitter/X (via API v2)

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
```

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
| `HERALD_GITHUB_TOKEN` | GitHub token for API access |
| `HERALD_REPOS` | Comma-separated repos (`owner/repo` or local paths) |
| `HERALD_DEFAULT_MODEL` | LLM model (default: `claude-sonnet-4-20250514`) |
| `HERALD_LOOKBACK_DAYS` | Default lookback period (default: 7) |
| `HERALD_DRY_RUN` | Set to `true` for preview-only mode |

## GitHub Actions

See `.github/workflows/release-announce.yml` for a ready-to-use workflow that:
- Posts release announcements when a GitHub Release is published
- Posts weekly digests every Monday
- Supports manual triggers with content type selection

## Multi-model quality (optional)

Herald can use [consilium](https://github.com/abrichr/consilium) for multi-model consensus on important posts:

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
git clone https://github.com/abrichr/herald.git
cd herald
uv sync --extra dev
uv run pytest -v
uv run ruff check .
```

## License

MIT
