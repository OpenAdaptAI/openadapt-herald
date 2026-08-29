# herald

Herald is internal social-copy tooling. It is not the OpenAdapt product.

> [!IMPORTANT]
> **Status: Internal tooling — not the product.** Herald drafts and posts
> release copy for the OpenAdapt team. It is dormant: it does not post on
> every commit, and it is not required by any OpenAdapt package.
>
> OpenAdapt compiles a demonstrated GUI task into a program that reports
> VERIFIED only if an independent check agrees. Recording authors. Receipt
> proves. Program is the company. Install via the
> [`OpenAdapt`](https://github.com/OpenAdaptAI/OpenAdapt) launcher
> (`pip install openadapt`); the engine is
> [`openadapt-flow`](https://github.com/OpenAdaptAI/openadapt-flow).
> Lifecycle labels for every repository are in the
> [repository lifecycle registry](https://github.com/OpenAdaptAI/.github/blob/main/REPOSITORY_LIFECYCLE.md).

If someone publishes a release digest, Herald's composer prompts use that
product noun. Composer copy never calls OpenAdapt generative RPA, an LMM
adapter, AI-first, verified last-mile as the product name, or something that
"learns by observing."

Herald can collect commits, releases, and merged PRs, fill a writing-guide-aware
prompt, and post to Discord, Twitter/X, and LinkedIn. That publish path still
calls Anthropic. It is opt-in, not a commit bot.

## Quick start

```bash
# Install
pip install herald-announce

# Configure (or set env vars)
cp .env.example .env
# Edit .env with your API keys

# Preview a product-correct spotlight. No Anthropic key.
herald compose --template --content-type spotlight

# Preview from git history (needs Anthropic unless --template)
herald preview --repos owner/repo --days 7

# Actually post to configured platforms
herald publish --repos owner/repo --content-type release
```

`--template` fills canned copy. The spotlight template is `openadapt quickstart --break-it`: an independent check rejects a fake success banner. `herald publish --template --dry-run` shows that copy without posting and without calling Anthropic.

LLM `compose` / `publish` still needs `HERALD_ANTHROPIC_API_KEY`. The free draft path is [Crier](https://github.com/OpenAdaptAI/openadapt-crier) plus `oa-social`. Use that when you want a draft and you don't want to pay for a composer call.

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

- `release` — Announce a specific release. On-demand, not every commit.
- `digest` — Weekly roundup across repos. On-demand.
- `spotlight` — Deep dive on a single feature. The shipped example is `--break-it`.

## CLI commands

```bash
herald collect   # Gather and display artifacts
herald compose   # Generate content (no posting)
herald compose --template --content-type spotlight  # canned --break-it copy, no LLM
herald preview   # Alias for compose
herald publish   # Full pipeline: collect → compose → post
herald publish --template --dry-run --content-type spotlight
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
| `HERALD_LINKEDIN_ACCESS_TOKEN` | LinkedIn OAuth2 access token (`w_member_social` scope) |
| `HERALD_GITHUB_TOKEN` | GitHub token for API access |
| `HERALD_REPOS` | Comma-separated repos (`owner/repo` or local paths) |
| `HERALD_DEFAULT_MODEL` | LLM model (default: `claude-sonnet-4-20250514`) |
| `HERALD_LOOKBACK_DAYS` | Default lookback period (default: 7) |
| `HERALD_DRY_RUN` | Set to `true` for preview-only mode |

## LinkedIn setup

To post to LinkedIn, you need an OAuth2 access token with the `w_member_social` scope:

1. Create an app at [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps)
2. Under **Products**, request access to **Share on LinkedIn** (grants `w_member_social`)
3. Generate an OAuth2 access token using the 3-legged OAuth flow or the Developer Portal token generator
4. Set `HERALD_LINKEDIN_ACCESS_TOKEN` in your `.env` file

Note: LinkedIn access tokens typically expire after 60 days. For long-lived automation, implement a token refresh flow or use a long-lived token from a LinkedIn app with appropriate permissions.

## GitHub Actions

See `.github/workflows/release-announce.yml` for a workflow that can post a
digest on demand. Herald is dormant. Do not wire it to post on every commit.

## Multi-model quality (optional)

Herald can use [consilium](https://github.com/OpenAdaptAI/openadapt-consilium) for multi-model consensus on important posts:

```bash
pip install herald-announce[consilium]
herald publish --use-consilium --repos owner/repo
```

This queries multiple LLMs, has them cross-review each other's drafts, and synthesizes the best version.

## Writing guide

`herald/prompts/writing_guide.md` is an embedded copy of the workspace
WRITING_GUIDE. Do not invent a second guide. The composer must:

- Use contractions
- Use no em-dash clusters (zero in tweets)
- Use no banned words
- Never write "it's not X, it's Y"

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
