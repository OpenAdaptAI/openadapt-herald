# Compliance and repository status

This page collects the platform terms, data handling, and repository status
that matter before you run Herald against real accounts.

## Platform terms

### LinkedIn

Section 3.1 of LinkedIn's
[API Terms of Use](https://www.linkedin.com/legal/l/api-terms-of-use) says
you must not use the APIs to automate posting on LinkedIn.

- `herald post --platform linkedin` never posts. It exits with `not_sent` and
  asks you to paste the text into LinkedIn yourself.
- `herald publish` still has a LinkedIn publisher that posts through the UGC
  Posts API when `HERALD_LINKEDIN_ACCESS_TOKEN` is set. This includes the
  scheduled workflow in `.github/workflows/release-announce.yml`, which
  passes that secret if it exists. Leave the token unset unless your use is
  allowed under LinkedIn's terms. Whether to remove or gate this publisher
  is an open decision.

### X

Posts made through the X API fall under X's
[developer policy](https://developer.x.com/en/developer-terms/policy). Read
it for the account you post from before the first live post, including what
it says about automated and AI-generated content.

Reading recent posts and creating a post are paid calls on X's pay-per-use
plans. `herald post --precheck-timeline` and every run after an `uncertain`
result read recent posts.

### Discord

Herald posts to Discord through a webhook you create for one channel. Anyone
with the webhook URL can post to that channel, so keep it secret.

## Data sent to model providers

`herald compose`, `herald preview`, and `herald publish` send the collected
material to Anthropic's API to draft posts:

- the subject, author, and date of each commit;
- the tag, name, and full notes of each release;
- the number, title, and author of each merged pull request, and the first
  500 characters of its description.

With `--use-consilium`, the same material also goes to OpenAI. Don't run
these commands on a private repository whose history you can't share with
those providers.

`herald collect` and `herald post` don't call a model. `herald post` sends
only the approved text to X.

## Records Herald keeps

`herald post` keeps an append-only JSON Lines ledger so a later run doesn't
post the same text twice. Each record holds the text's SHA-256 (not the text
itself), the platform, the result, a timestamp, and the post id and URL once
the post exists. [herald-post.md](herald-post.md) describes how the ledger
works. The other commands keep no records.

## Repository status

The OpenAdapt team built Herald for its own announcements. It isn't part of
the OpenAdapt product, and no OpenAdapt package depends on
it. The product is the demonstration compiler
[`openadapt-flow`](https://github.com/OpenAdaptAI/openadapt-flow), installed
with `pip install openadapt` from the
[`OpenAdapt`](https://github.com/OpenAdaptAI/OpenAdapt) launcher. The
lifecycle label for each OpenAdapt repository is in the
[repository lifecycle registry](https://github.com/OpenAdaptAI/.github/blob/main/REPOSITORY_LIFECYCLE.md).
