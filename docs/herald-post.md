# Posting approved text with `herald post`

`herald post` posts text a person has already reviewed to X. It doesn't call a
model, and it never shortens or rewrites the text. If the text is too long, it
refuses and tells you by how much.

```bash
herald post --file approved.txt --platform x \
  --ledger post-ledger.jsonl \
  --expect-sha256 <approved content_sha256> \
  --precheck-timeline
```

## Checks before sending

- **Approval hash.** The SHA-256 of the text must match `--expect-sha256`, so
  an edit after approval stops the post. Herald hashes the file's text without
  its trailing newlines. To get that hash, run
  `herald post --file approved.txt --dry-run --json` and copy
  `content_sha256`.
- **Length.** The text must fit X's 280 weighted characters. X counts every
  link as 23 characters and most CJK characters and emoji as 2. Herald counts
  the same way and leans long when it can't tell whether X will treat a word
  as a link. A link written without `https://` counts as 23 or its full
  length, whichever is longer. If X still refuses the text as too long, the
  result is `not_sent`.
- **Ledger.** The ledger must have no record that this exact text was already
  posted.

## Results

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

## After an `uncertain` result

Herald doesn't retry on its own. The next run reads the account's 20 most
recent posts first. If the text is there, the ledger records it as published
and nothing is sent. If it isn't there yet and the attempt was less than 2
minutes ago, the result stays `uncertain` and you run again later. After
that, Herald records the check and asks you to run again with `--retry`. A
`--retry` run reads the recent posts once more before it sends.

## The ledger

The ledger is an append-only JSON Lines file keyed by the SHA-256 of the
text. Herald writes an `uncertain` record before each request, so a crash or
a cancelled job also leaves a record that the next run checks.

- Keep the ledger somewhere that outlasts the job. A GitHub-hosted runner's
  disk is wiped after each job.
- Run one `herald post` at a time per ledger, because two runs at once can
  both send. In GitHub Actions, a concurrency group is enough.
- With `--precheck-timeline`, Herald also skips the post if the text is among
  the account's 20 most recent posts. This covers a lost ledger.
- Set the ledger path with `--ledger` or `HERALD_POST_LEDGER` (environment or
  `.env`). A live post requires one.

## Dry runs

`--dry-run` runs the local checks (hash, length, ledger) and never opens the
X account. `HERALD_DRY_RUN=true` has the same effect. A dry run reads the
ledger, so a dry run after an `uncertain` attempt also reports `uncertain`.

## LinkedIn

`herald post --platform linkedin` exits with `not_sent` and asks you to paste
the text into LinkedIn yourself. See [COMPLIANCE.md](COMPLIANCE.md) for why.

## Cost

Reading recent posts and creating a post are paid X API calls on
pay-per-use plans. Check the current prices in the X developer console.
