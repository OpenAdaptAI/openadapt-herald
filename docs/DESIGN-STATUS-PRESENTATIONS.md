# Auto-generated Status Presentations: Design Options

Status: Draft for review
Owner: richard.abrich@mldsai.com
Related: [README.md](../README.md), [DESIGN-ADO-SUPPORT.md](DESIGN-ADO-SUPPORT.md)

## 1. Problem statement

Weekly / biweekly status updates are expensive to assemble by hand. Everything
that needs to be in the deck already exists in CI:

- **What shipped** — commits, merged PRs, releases, closed work items (the
  same artifacts herald already collects).
- **What it looks like when it works** — the Playwright E2E suite is already
  run by both the coding agent and the human reviewer as part of the
  "did it actually work?" check in our agentic-dev loop. Each passing test
  is a scripted, reproducible walkthrough of a user flow.

We want a tool that:

1. Collects the "what shipped" artifacts (reuse herald's collector).
2. Captures the "what it looks like" media by recording tagged Playwright
   runs to animated GIFs.
3. Assembles a status-update deck linking the two.
4. Delivers the deck somewhere useful (Drive, SharePoint, Teams, a repo).

The dev-loop integration is the key leverage point: the Playwright tests
**already exist** and **already run** for correctness. Recording them for
status media is nearly free.

## 2. Shape of the problem vs herald

Herald's pipeline is `Collect → Compose → Publish`. Presentations are the
same pipeline with different implementations:

| Stage | Herald today | Presentations |
|-------|-------------|---------------|
| Collect | Git, GitHub, (soon ADO) | + Playwright runs → GIFs |
| Compose | LLM → platform-specific text | LLM → slide outline + layout |
| Publish | Discord / Twitter / LinkedIn | .pptx / .pdf / Slides / hosted HTML |

**Collector is reusable verbatim.** The diff is the media capture step, a
fundamentally different composer, and different delivery backends.

## 3. Where should this live?

Three options. Pick one before writing any code.

### 3.A As a new `content_type` inside herald

Add `"presentation"` alongside `release` / `digest` / `spotlight`
(`herald/composer.py:13`). The composer returns a slide-structured dict;
new `PptxPublisher` / `SlidesPublisher` subclass `Publisher`.

- **Pros:** zero duplication of collector / config / CLI; one install.
- **Cons:** bloats herald's dependency tree with `python-pptx`, `playwright`,
  `ffmpeg`-wrangling code. Herald today is `pip install herald-announce`,
  tiny; that posture dies.

### 3.B New sibling package `openadapt-presenter` that depends on herald

Herald stays focused on social. Presenter imports `herald.collector` and
adds media capture, slide composition, and slide publishing.

- **Pros:** clean single-responsibility split; heavy deps (`playwright`,
  `python-pptx`, `ffmpeg`) live in their own package; separate release
  cadence.
- **Cons:** two packages to version; need to be disciplined about what
  stays in herald vs moves to a shared lib.

### 3.C Extract a `openadapt-artifacts` shared lib; herald and presenter both depend on it

The cleanest long-term shape: `openadapt-artifacts` owns the dataclasses
(`Commit`, `PullRequest`, `Release`, new `WorkItem`, new `Screencast`) and
the collectors. Herald becomes a thin social publisher; presenter is a
thin slide publisher.

- **Pros:** right factoring if we're going to have 3+ consumers (social,
  presentations, internal changelog, investor update, ...).
- **Cons:** the most upfront work; premature if presenter is the only
  second consumer for the foreseeable future.

**Recommendation: 3.B now, 3.C when the third consumer shows up.** Start
the repo as `openadapt-presenter`. If and when a third "collect git stuff
and format it somehow" tool appears, lift `herald.collector` out.

## 4. Options by subsystem

### 4.1 Output format

What the deck actually is.

#### F1 — `python-pptx` → .pptx

Generate a PowerPoint file. Put GIFs on slides via `slide.shapes.add_picture()`
(pptx supports animated GIFs; they animate in Slide Show mode).

- **Pros:** universally editable by stakeholders after the fact; renders
  offline; plays well with SharePoint / Teams / Outlook; executives expect
  pptx. Mature library.
- **Cons:** GIF playback quality is variable across pptx renderers (macOS
  Keynote sometimes shows only the first frame); no easy "live" mode;
  styling is imperative and verbose.

#### F2 — Marp / reveal.js (markdown → HTML slides)

Author in Markdown, render with Marp CLI or reveal.js. GIFs are just
`![](path.gif)`.

- **Pros:** diffable source of truth (Markdown in git); browser-native GIF
  playback; trivially hostable on GitHub Pages; version history for free;
  very fast LLM output target.
- **Cons:** non-technical stakeholders can't easily edit; "download as pptx"
  via Marp works but is lossy; less "proper deck" feel.

#### F3 — Google Slides API

Build the deck directly in Drive.

- **Pros:** collaborative editing, comments, share links; lives in the tool
  execs already use.
- **Cons:** Google Workspace dependency; OAuth setup; the Slides API is
  fiddly (batch-update JSON); GIFs must be hosted somewhere Google can fetch
  from (not inline); API quotas.

#### F4 — HTML → print to PDF

Render a static HTML deck (Marp/reveal), then headless-Chrome to PDF.

- **Pros:** no moving GIFs in a PDF, but you get a durable artifact; fine for
  archival / email.
- **Cons:** loses the whole point of animated walkthroughs. Only as a
  supplementary output.

#### F5 — AI-native deck tools (Gamma, Tome, etc.)

Out of scope — vendor lock-in, opaque output, can't embed arbitrary recorded
GIFs reliably.

**Recommendation: F2 as the source of truth, F1 as a rendered export.**
Author Marp Markdown (committed to git, diffable, LLM-friendly); export to
pptx and HTML from the same source. Covers the "editable by execs" and
"diffable / live" needs without forcing a choice.

### 4.2 Media capture

#### M1 — Playwright `page.video()` → ffmpeg → GIF

Enable `recordVideo` on the browser context; Playwright writes webm; convert
to GIF with ffmpeg (`-vf "fps=12,scale=960:-1:flags=lanczos"` + palettegen).

- **Pros:** zero test code changes; captures exactly what the user would see;
  works for any test; one knob for fps / size tradeoff.
- **Cons:** captures the full test including setup noise — needs trimming;
  webm → GIF is CPU-heavy; GIFs get big fast (5–20 MB per flow).

#### M2 — Playwright screenshot sequence → ffmpeg → GIF

Insert `await page.screenshot()` calls at interesting moments, stitch with
ffmpeg.

- **Pros:** author controls exactly which frames; smaller output; no
  capture-of-irrelevant-stuff problem.
- **Cons:** requires editing test code; timing across screenshots can look
  jerky; loses hover / animation detail between frames.

#### M3 — Playwright trace viewer

Playwright `--trace on` produces a rich interactive trace.

- **Pros:** captures everything, DOM-level; invaluable for debugging.
- **Cons:** interactive HTML viewer, not a GIF. Wrong artifact for a deck.
  Mention and move on.

#### M4 — Annotation-based opt-in

Tests tag themselves as presentation-eligible, e.g.
`test.describe('login flow', { tag: '@demo' }, ...)` or
`test.info().annotations.push({ type: 'screencast', title: '...' })`. The
capture runner only records tagged tests.

- **Pros:** explicit opt-in; stable contract between authors and presenter;
  decouples "I want this on the deck" from "I want CI to check this".
- **Cons:** authors need to remember to tag; initial rollout drudgery.

#### M5 — Separate "demo" suite

Keep demo recordings in `tests/demos/*.spec.ts`, run with its own Playwright
project config. Recording is the whole point; presenter always recordings
these.

- **Pros:** zero ambiguity; can add narrator-style pacing (intentional
  `page.waitForTimeout`, pretty viewport size) without polluting
  correctness tests.
- **Cons:** duplicates test logic; violates the "one test doubles as proof
  and demo" premise the user asked for.

**Recommendation: M1 + M4.** Record video on *tagged* tests only, convert to
GIF out-of-band. Honors the "tests already serve both roles" goal while
keeping the capture cost bounded.

Open choice: GIF vs short MP4. MP4 is 5-10× smaller and plays fine in
reveal.js / HTML decks, but pptx prefers GIF. **Emit both**, let the output
format pick.

### 4.3 Slide composition

#### S1 — Pure template

Fixed template: "Title → This Week → Feature per slide → Metrics → Next
Week". Variables filled from artifacts. No LLM involvement.

- **Pros:** predictable, fast, free.
- **Cons:** looks like it was generated; misses narrative.

#### S2 — LLM-driven outline + template layout

LLM produces a structured outline (JSON: `[{title, bullets, media_tag}, ...]`);
renderer turns each outline item into a slide using a template per slide
type. The LLM never sees pptx/HTML, only JSON.

- **Pros:** narrative quality of an LLM; visual predictability of a
  template; reuses herald's writing-guide prompt (`prompts/writing_guide.md`)
  verbatim to avoid AI-sounding output in the narration.
- **Cons:** two-stage pipeline to maintain; LLM can hallucinate references to
  features / media that don't exist — needs a validation pass that drops
  broken references.

#### S3 — LLM writes full Marp/HTML source

Dump artifacts in, ask the LLM to emit Marp markdown.

- **Pros:** maximum flexibility; simplest pipeline.
- **Cons:** least controllable visual output; LLM may produce inconsistent
  slide styles across runs; harder to diff "this week vs last week."

**Recommendation: S2.** Same architectural shape as herald's composer
(`herald/composer.py:72`): LLM returns a JSON the code then renders.

### 4.4 Media linking

How the composer knows which GIF goes on which slide.

- Each captured test emits a manifest entry:
  `{tag: "login-happy-path", title: "...", gif: ".../login.gif", mp4: ".../login.mp4", pr_numbers: [...]}`.
- PR numbers are inferred by matching test-file touch history
  (`git log tests/demos/login.spec.ts`) against the window's PRs — a heuristic,
  good enough for v1.
- The composer sees the manifest in the prompt and is asked to reference
  media by tag. The renderer resolves tag → file. Broken references are
  dropped at render time, not silently.

### 4.5 Delivery

#### D1 — Commit to a `status-updates` repo / branch

Rendered deck (Marp MD + exported pptx + GIFs) committed on a
`status/YYYY-WW` branch; PR opened for review.

- **Pros:** reviewable, versioned, no new auth.
- **Cons:** GIFs inflate git history fast. Git LFS or a separate CDN mitigates.

#### D2 — Upload to Google Drive / SharePoint

Drop the pptx in the shared folder execs already check.

- **Pros:** meets stakeholders where they are.
- **Cons:** OAuth per backend; no version history beyond the tool's own.

#### D3 — Host the HTML deck on Pages / static site

`reveal.js` deck at `status.<project>.dev/2026-W15/`.

- **Pros:** shareable link, plays GIFs natively, small hosting footprint.
- **Cons:** if the repo is private, auth on the static host is nontrivial
  (Cloudflare Access / Netlify Identity / GitHub Pages private).

#### D4 — Post a link via herald's existing publishers

Once the deck is hosted (D3) or attached (D1), herald's Teams / Discord /
Slack publishers can post the announcement with the link. Clean handoff;
keeps herald doing the one thing it's good at.

**Recommendation: D1 (committed artifacts) + D4 (post link via herald).**
Skip D2/D3 until someone asks for them. D1+D4 reuses existing plumbing.

## 5. Recommended v1

```
openadapt-presenter/
  presenter/
    __init__.py
    cli.py                  # `presenter build --week 2026-W15`
    capture.py              # Playwright runner, video→gif, manifest
    compose.py              # artifacts + manifest → slide-outline JSON (LLM)
    render/
      marp.py               # outline JSON → Marp markdown
      pptx.py               # outline JSON → .pptx via python-pptx
    templates/
      status-weekly.md.j2   # Marp template
    prompts/
      status.md             # "you're writing a status deck" system prompt
  tests/
  pyproject.toml            # depends on: herald-announce, playwright, python-pptx, jinja2, anthropic
```

Scope:

1. **Collector:** `from herald.collector import collect_all`. No new code.
2. **Capture:** `presenter capture` runs Playwright with video for
   `@demo`-tagged tests (M1 + M4); ffmpeg-converts to GIF and MP4;
   writes `captures/manifest.json`.
3. **Compose:** LLM call with the artifacts text + manifest; returns
   validated slide-outline JSON (S2). Reuses `herald/prompts/writing_guide.md`.
4. **Render:** Marp Markdown (primary). Export via `marp --pdf` / `marp --pptx`
   as needed.
5. **Deliver:** write to `status-updates/YYYY-WW/` on a branch in the calling
   repo; optionally call `herald publish` with the resulting link.
6. **One example workflow:** a `.github/workflows/status-weekly.yml` or ADO
   pipeline equivalent that runs on a cron, records GIFs, renders, opens a PR.

Explicitly **out of scope for v1:** Google Slides, SharePoint upload,
headless-CDN hosting, narration audio / text-to-speech, per-PR animated
changelog entries, multi-repo aggregation, Gamma-style "make it pretty"
post-processing.

## 6. How this interacts with the agentic dev loop

This is the "why now" for this tool. Stating it plainly so the design can
be evaluated against it:

- The Playwright tests are a **contract**: the agent writes code, the tests
  pass, the human reviewer watches (or re-runs) them to confirm the feature
  works end-to-end.
- Recording them gives us a **durable visual receipt** of each passing
  contract. Regressions are visible as GIF diffs between runs, not just red
  CI.
- At status-update time, these receipts are already sitting in CI artifacts.
  The presenter just picks the latest for each `@demo` tag and embeds them.
- Follow-on: the *same* GIFs can flow into product docs, launch blog posts,
  and the `openadapt-maintenance` docs site. Write once, show everywhere.

This means **tagging matters more than the deck tooling**. Whatever we
build, the `@demo` tag should be the stable interface between test authors
and downstream consumers.

## 7. Risks and open questions

- **Flakiness.** If a tagged test is flaky, the deck has a hole or a weird
  frame. Policy: presenter uses the last **green** run for each tag, not
  the most recent run.
- **GIF size.** 10–20 MB per flow × 8 flows = a heavy deck. Mitigation:
  max-length cap (e.g. 15 s), aggressive palette / fps tuning,
  prefer MP4 in HTML, only GIF in pptx. Consider lossy WebP as a middle
  ground.
- **PII / customer data in recordings.** Playwright captures everything on
  screen. Hook `openadapt-privacy` into the capture step, or mandate
  test-only fixture data. See memory rule: never surface enterprise customer
  names in public content.
- **Cross-browser consistency.** Test under Chromium only for recording; let
  correctness tests still run in all browsers.
- **Ownership of the "demo" tag semantics.** Needs a one-page contract
  doc: naming convention for tags, viewport size, what counts as a "flow,"
  max duration.
- **LLM cost.** Weekly + monthly + per-release = not free. Reuse
  consilium only for high-stakes decks (launches); default to single-model.
- **Platform coverage.** Playwright covers web. For desktop flows, the
  `openadapt-capture` package in this monorepo already records cross-platform
  desktop; a later iteration can treat desktop captures as a second source.
  Do not block v1 on this.

## 8. Follow-up tickets (not in v1)

- Google Slides publisher.
- Desktop-flow capture via `openadapt-capture`.
- Narration: per-slide TTS + embedded audio track.
- Animated per-PR changelog entries (short GIF per merged PR).
- A `presenter diff` command: "what changed visually between last week and
  this week" (GIF diff per tag).
- Hosted web viewer on `status.openadapt.ai`.
- Auto-redaction pass using `openadapt-privacy` on every GIF.

## 9. TL;DR

- Reuse herald's collector; build a sibling package `openadapt-presenter`.
- Capture: tagged Playwright tests → video → GIF + MP4 + manifest.
- Compose: LLM returns a JSON slide outline (same shape as herald's
  composer), not raw markup.
- Render: Marp Markdown as source of truth, with pptx/PDF exports.
- Deliver: commit to a `status-updates/` folder, announce via herald.
- The real lock-in point is the `@demo` tag contract on Playwright tests —
  get that right, everything else is swappable.
