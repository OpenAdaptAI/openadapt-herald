# Herald

Herald drafts release announcements and weekly digests from your git history
and posts them to Discord, X, and LinkedIn. It reads commits, GitHub releases,
and merged pull requests, and asks Claude for one draft per platform.
`herald preview` only prints the drafts. `herald publish` drafts and posts in
one step, without asking first.

It's for maintainers who want to announce what shipped without writing every
post by hand. The OpenAdapt team built it for its own announcements, and it
works with any git repository.

## Quick start

Herald needs Python 3.10 or later. It isn't on PyPI yet, so install it from
GitHub:

```bash
pip install "git+https://github.com/OpenAdaptAI/openadapt-herald.git"
```

From inside any git checkout, list what Herald would write about. This step
needs no keys:

```bash
herald collect --repos . --days 30
```

Draft posts with Claude. This prints the drafts and posts nothing:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
herald preview --repos . --days 30 --content-type digest
```

To post, set up at least one platform (see [Configuration](#configuration)),
then run `publish` with `--dry-run` first to see what it would send:

```bash
herald publish --repos . --days 30 --content-type digest --dry-run
```

## What Herald reads

`--repos` takes a comma-separated list. Each entry is one of:

- A local path, such as `.` or `/path/to/repo`. Herald reads commits with
  `git log`.
- A GitHub `owner/repo`. Herald reads releases and merged pull requests with
  the [GitHub CLI](https://cli.github.com/) (`gh`), so `gh` must be installed
  and either signed in or given a token through `HERALD_GITHUB_TOKEN`.

`--days` sets how far back to look. Without it, Herald uses
`HERALD_LOOKBACK_DAYS`, which defaults to 7.

## How it works

```
Collect          Compose               Publish
git log    ──►   Claude drafts    ──►  Discord webhook
gh releases      one post per          X API v2
gh pr list       platform, using       LinkedIn UGC Posts API
                 the writing guide
```

1. **Collect** gathers commits, releases, and merged pull requests.
2. **Compose** sends them to Claude with a writing guide and asks for one
   draft per platform.
3. **Publish** posts each draft to the platforms you configured.

## Content types

- `release`: announce one release. Suits a release event.
- `digest`: a weekly roundup across repositories. Suits a schedule.
- `spotlight`: a closer look at one feature. Suits a manual run.

## Commands

```bash
herald collect   # Show what herald found
herald compose   # Draft posts (no posting)
herald preview   # Same as compose
herald publish   # Collect, draft, and post
herald post      # Post approved text exactly as written (no model call)
```

Run `herald <command> --help` to see every option.

## Post approved text exactly as written

`herald post` posts text a person has already reviewed to X. It doesn't call a
model and never shortens or rewrites the text. If the text is too long, it
refuses and says by how much.

```bash
herald post --file approved.txt --platform x \
  --ledger post-ledger.jsonl \
  --expect-sha256 <approved content_sha256> \
  --precheck-timeline
```

Before sending, it checks that:

- The text's SHA-256 matches `--expect-sha256`, so an edit after approval
  stops the post. To get the hash, run
  `herald post --file approved.txt --dry-run --json` and copy `content_sha256`.
- The text fits X's 280 weighted characters. Like X, Herald counts a link as
  23 characters and most CJK characters and emoji as 2.
- The ledger, an append-only JSON Lines file, has no record that this text was
  already posted.

Each run ends with one result and exit code:

| Result | Exit code | Meaning |
|---|---|---|
| `published` | 0 | The post is on X and recorded in the ledger. |
| `not_sent` | 3 | Herald didn't post. |
| `uncertain` | 4 | A request may have reached X. The next run checks the account's recent posts before it sends again. |

`--dry-run` (or `HERALD_DRY_RUN=true`) runs only the local checks and never
contacts X.
[docs/herald-post.md](https://github.com/OpenAdaptAI/openadapt-herald/blob/main/docs/herald-post.md)
covers the ledger, retries after an `uncertain` result, and character counting.

## Configuration

Herald reads settings from the environment or from a `.env` file in the
current directory. Every setting uses the `HERALD_` prefix. To start from the
example file, copy
[`.env.example`](https://github.com/OpenAdaptAI/openadapt-herald/blob/main/.env.example)
to `.env`.

| Variable | Description |
|----------|-------------|
| `HERALD_ANTHROPIC_API_KEY` | Anthropic API key for drafting. If it's empty, Herald uses `ANTHROPIC_API_KEY` from the environment. |
| `HERALD_DISCORD_WEBHOOK_URL` | Discord webhook URL |
| `HERALD_TWITTER_CONSUMER_KEY` | X API consumer key |
| `HERALD_TWITTER_CONSUMER_SECRET` | X API consumer secret |
| `HERALD_TWITTER_ACCESS_TOKEN` | X API access token |
| `HERALD_TWITTER_ACCESS_TOKEN_SECRET` | X API access token secret |
| `HERALD_LINKEDIN_ACCESS_TOKEN` | LinkedIn OAuth2 access token (`w_member_social` scope) |
| `HERALD_GITHUB_TOKEN` | GitHub token that Herald passes to `gh`. If it's empty, Herald uses `GH_TOKEN` from the environment. |
| `HERALD_REPOS` | Default for `--repos` |
| `HERALD_DEFAULT_MODEL` | Claude model for drafting (default: `claude-sonnet-4-20250514`) |
| `HERALD_LOOKBACK_DAYS` | Default for `--days` (default: 7) |
| `HERALD_DRY_RUN` | Set to `true` to preview without posting |
| `HERALD_POST_LEDGER` | Ledger file for `herald post` (required for a live post) |

Posting to X needs all four `HERALD_TWITTER_*` values.

### LinkedIn token

`herald publish` needs an OAuth2 access token with the `w_member_social`
scope to post to LinkedIn:

1. Create an app in the
   [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps).
2. Under **Products**, request **Share on LinkedIn**, which grants
   `w_member_social`.
3. Generate a token with the 3-legged OAuth flow or the portal's token
   generator.
4. Set `HERALD_LINKEDIN_ACCESS_TOKEN`.

LinkedIn tokens usually expire after 60 days. Read [Limits](#limits) before
you turn on LinkedIn posting.

## GitHub Actions

[`.github/workflows/release-announce.yml`](https://github.com/OpenAdaptAI/openadapt-herald/blob/main/.github/workflows/release-announce.yml)
runs `herald publish` with the `digest` content type every Monday at 15:00
UTC. You can also start it by hand and choose the content type, the number of
days, and a dry run. It doesn't run on release events, so to announce a
release, start it by hand with the `release` content type. The workflow lists
OpenAdapt repositories in `HERALD_REPOS`; change that list if you copy it.

## Drafts from several models (optional)

With the `consilium` extra, Herald sends the same prompt to Claude and GPT-4o
through [consilium](https://github.com/OpenAdaptAI/openadapt-consilium) and
uses the longer of the two drafts.

```bash
pip install "herald-announce[consilium] @ git+https://github.com/OpenAdaptAI/openadapt-herald.git"
export ANTHROPIC_API_KEY=sk-ant-... OPENAI_API_KEY=sk-...
herald publish --use-consilium --repos owner/repo --dry-run
```

consilium reads `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` from the environment
only, not from `.env`.

## Writing guide

The prompt includes a
[writing guide](https://github.com/OpenAdaptAI/openadapt-herald/blob/main/herald/prompts/writing_guide.md)
that lists common signs of machine-written text, such as stock words
("delve", "leverage"), rule-of-three lists, and uniform sentence length, with
an instruction against each. It draws on Wikipedia's "Signs of AI writing"
and the research listed at the end of the guide.

## Limits

- Version 0.1.0. Herald isn't published to PyPI.
- Drafts come from a model. Read them with `preview` or `--dry-run` before you
  post.
- `herald publish` cuts X drafts at 280 plain characters. `herald post`
  refuses text that's too long instead of cutting it.
- LinkedIn's API terms (section 3.1) don't allow automated posting.
  `herald post` never posts to LinkedIn, but `herald publish` does when
  `HERALD_LINKEDIN_ACCESS_TOKEN` is set. Leave it unset unless your use is
  allowed.
- Run one `herald post` at a time per ledger. Two runs at once can both send.
- `herald post` counts an emoji joined with a zero-width joiner or a
  skin-tone modifier as longer than X does, so it refuses some posts that X
  would accept.
- With `--use-consilium`, both models also review the drafts, but the reviews
  go unused. Herald caps consilium at $0.10 per run by consilium's cost
  estimate, the drafts and reviews reach that cap, and consilium then skips
  the step that combines the drafts.
- Reading recent posts and creating a post are paid calls on X's pay-per-use
  plans.

Platform terms, the data Herald sends to model providers, and this
repository's status are in
[docs/COMPLIANCE.md](https://github.com/OpenAdaptAI/openadapt-herald/blob/main/docs/COMPLIANCE.md).

## Development

```bash
git clone https://github.com/OpenAdaptAI/openadapt-herald.git
cd openadapt-herald
uv sync --extra dev
uv run pytest
uv run ruff check .
```

## License

MIT
