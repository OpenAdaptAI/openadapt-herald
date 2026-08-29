<!--
Embedded copy of the workspace WRITING_GUIDE constraints for LLM composition.
Canonical source: workspace WRITING_GUIDE.md (beside AGENTS.md / CLAUDE.md).
Do not invent extra rules here. If they conflict, the workspace copy wins.

Composer extract of the four mechanical checks:
- Contractions: use them (don't, can't, it's). Zero contractions reads as machine output.
- No em-dash clusters. Maximum one em dash per three paragraphs. Zero in tweets and other short copy.
- No banned words (see the taxonomy).
- No "it's not X, it's Y" framing. State the claim and support it.
-->

# Writing That Doesn't Sound Like an LLM

A project-agnostic reference. Based on AI detection research, Wikipedia's "Signs of AI Writing" page, and practical discussion from 2024-2026. Updated July 2026 with a full taxonomy: for each tell, what it is, why models produce it, how to detect it, and the prompt instruction that actually suppresses it.

One meta-lesson from the 2026 literature before the lists: word blacklists alone don't work. A model told "never say delve" says "dig into" in the same dead rhythm. The tells that matter are structural and rhythmic, and the counters that work are constraints on how the text is built, not just which words it uses. Ban the words anyway (they're cheap true positives for readers), but put your effort into structure, rhythm, and stakes.

## How detectors work

Two main signals:

Perplexity measures how predictable your word choices are. LLMs pick the statistically most likely next word, which makes their output low-perplexity. Human writing is messier. We use idioms, unexpected metaphors, sentence fragments. A perplexity score above 85 reads as more human (per GPTZero).

Burstiness measures variation in sentence length across a document. Humans write in bursts. A long winding sentence, then a short one. Then maybe three medium ones. LLMs produce sentences of roughly the same length, one after another, like a metronome.

Human readers use neither. They notice register: text that's competent but flat, enthusiastic about nothing in particular, certain about everything, and attached to no one. Frequent LLM users are reliably better at spotting AI text than commercial detectors (arXiv 2501.15654) — and what they key on is the stuff in the taxonomy below.

---

## The taxonomy

Five families. Each entry: the tell, why it happens, how to detect it, and the prompting counter — instruction wording that reliably suppresses it when you're directing an agent (or yourself).

### 1. Lexical tells

**The AI-vocab cluster.**
- Tell: delve, tapestry, landscape, realm, intricate, pivotal, crucial, underscore, foster, testament, nuanced, comprehensive, vibrant, robust, meticulous, leverage, harness, embark, beacon, enhance, seamless, transformative, groundbreaking, game-changer, paradigm, synergy, empower, streamline, elevate, unlock, unleash, holistic, multifaceted, cutting-edge, "quiet" as an intensifier ("quiet confidence" — a 2026 arrival), plus connective tissue: furthermore, moreover, notably, subsequently, consequently, additionally.
- Why: RLHF and training data skew toward a safe, formal, slightly promotional register. These words spiked 50%+ in published text after ChatGPT launched, which is exactly what makes them detectable.
- Detect: grep the list. Also the out-loud test — would you say this word to a colleague? "Leverage" fails. "Use" passes.
- Counter: "Banned words: [list]. If you'd never say the word out loud to a coworker, don't write it. Prefer the plain verb: use, build, show, fix, run." And know the limit: a word ban without the structural counters below just produces synonym-shuffled LLM prose.

**Stock phrases.**
- Tell: "it's worth noting", "it is important to note", "in today's fast-paced world", "in the ever-evolving landscape of", "plays a vital role", "stands as a testament", "let's dive in", "the key takeaway", "at its core", "when it comes to", "in the realm of", "navigating the complexities of", "based on the information provided". Also the fake-casual tier: "Here's the kicker", "And honestly? That's rare."
- Why: high-frequency n-grams in training data; they're the lowest-perplexity way to open, connect, or close a thought.
- Detect: grep. Every one of these is deletable without losing a fact — that's the test.
- Counter: "Delete any phrase that could be removed without losing information. No throat-clearing: the first sentence of the piece and of every section must contain a fact or claim specific to this piece."

**Adjective inflation.**
- Tell: every noun wears an intensifier — powerful, seamless, robust, incredible, truly, deeply. Claims are carried by adjectives instead of evidence.
- Why: models are tuned toward enthusiasm and reader-pleasing; adjectives are free, numbers are not.
- Detect: for each adjective ask "compared to what?" If there's no answer in the text, it's inflation. High adjective-to-number ratio is the smell.
- Counter: "No adjective may carry a claim that a number or example could carry. State the number instead. Cut every intensifier (very, truly, incredibly, deeply)."

### 2. Structural tells

**Rule-of-three addiction.**
- Tell: everything comes in threes — "faster, cheaper, and more reliable"; three examples, three clauses, three bullet groups. AI adds a third item even when only two exist.
- Why: triads are the highest-probability rhetorical closure in English prose; the model reaches for symmetry the way water finds level.
- Detect: count three-item parallel constructions. More than one per page is suspicious; several per section is diagnostic.
- Counter: "Lists of exactly three parallel items are banned. Use two, or four, or one — or let the third item break the pattern (different length, different register, a joke)."

**The "It's not X — it's Y" contrast scaffold.**
- Tell: "It's not just a tool — it's a platform." "This isn't about speed; it's about trust." Plus cousins: "not only X but Y", "less about X, more about Y", "X isn't the point. Y is." Sam Kriss described being "driven to the point of fury" by this construction, and by 2026 readers see it as a flashing light.
- Why: cheap profundity. The frame manufactures a reversal without needing an actual insight, and reward models rate it as punchy.
- Detect: grep for "not just", "isn't just", "it's not about", "— it's". One instance can be earned; two is a pattern.
- Counter: "State the claim directly. If you write 'it's not X, it's Y', delete the first half and keep 'it's Y' — then justify Y with evidence instead of contrast."

**Em-dash density.**
- Tell: an em dash every 60-70 words, often two per sentence, doing jobs commas and periods should do.
- Why: the dash is a universal connector; it lets the model glue clauses without committing to their logical relationship.
- Detect: count them. More than one per ~150 words reads as AI in 2026, fairly or not.
- Counter: "Maximum one em dash per three paragraphs. Rewrite dash-asides as separate sentences, parentheses, or cut them."

**Uniform paragraph lengths.**
- Tell: every paragraph is 3-4 sentences, like bricks from the same mold. Sections are all the same length too.
- Why: the model's sense of "a paragraph" is an average over its training data; nothing pushes it off the mean.
- Detect: squint at the page. If the gray blocks are all the same size, it's the mold.
- Counter: "Vary paragraph length deliberately: at least one single-sentence paragraph per page, at least one long one. Section lengths should follow the importance of their content, not symmetry."

**Every-section-gets-a-list (and bold-lead bullets restated).**
- Tell: no section is allowed to be plain prose; each gets bullets, often with a bolded lead phrase immediately reworded in the sentence that follows ("**Scalable architecture**: The architecture is designed to scale...").
- Why: chat-optimized formatting. Lists score well for scannability in RLHF, so the model reaches for them even in essays.
- Detect: count sections with lists vs. without. Check bullets for the bold-restate pattern.
- Counter: "Default to prose. Bullets only for genuine enumerations (commands, spec items, tables of numbers) — never for argument. Never bold the first words of a bullet and then restate them."

**Summary paragraphs that restate the header (and conclusion-itis).**
- Tell: sections open by paraphrasing their own heading and close by summarizing what they just said; the piece ends with "In conclusion" / "Ultimately" recapping everything.
- Why: the five-paragraph-essay skeleton is heavily represented in training data, and summarizing is the model's lowest-risk move.
- Detect: delete the first and last sentence of each section. Did the piece lose any information? Then they were filler.
- Counter: "Never restate a heading in the section's first sentence. No recap endings: end on the last new thought, and it's allowed to land abruptly."

**Hedged both-sidesing.**
- Tell: every claim comes with a symmetric counterweight ("however, it's important to consider...") until the piece has no position left. Balance as a tic, not a judgment.
- Why: trained neutrality. Taking a side risks reward-model penalty; hedging never does.
- Detect: can you state, in one sentence, what the piece believes? If not, it both-sided itself to death.
- Counter: "Take a position and hold it. Address the strongest counterargument only where it genuinely threatens the claim, and answer it — don't just acknowledge it."

### 3. Rhythm tells

**No short sentences — nothing ever lands.**
- Tell: sentence lengths cluster at 20-25 words. No sentence under eight words in the whole piece. Every point is cushioned.
- Why: low-perplexity generation regresses to the mean sentence; a hard four-word sentence is a statistical outlier the model avoids.
- Detect: find the shortest sentence in the piece. If it's over 10 words, the piece has no punch anywhere.
- Counter: "Vary sentence length deliberately: some under six words, some over thirty. After the longest sentence in each section, land a short one. Let it land."

**No fragments.**
- Tell: every sentence is grammatically complete. Textbook English, no elisions, no "Then the fun part." standing alone.
- Why: grammar-following is deeply rewarded; fragments look like errors to a reward model.
- Detect: zero fragments in a 1,000-word informal piece is itself a tell.
- Counter: "Sentence fragments are allowed and encouraged where they add punch. Not everywhere. Where they land."

**Metronome paragraphs.**
- Tell: low burstiness — each sentence roughly the length of its neighbor, so the prose ticks. Reading aloud, you can nod on the beat.
- Why: same regression to the mean, at paragraph scale.
- Detect: read it aloud. If your breathing falls into a rhythm, it's the metronome.
- Counter: "Write in bursts: a long winding sentence, then a short one, then a couple of medium ones. Never three sentences of similar length in a row."

**Parallelism everywhere.**
- Tell: every clause balanced against its twin ("where X does A, Y does B; where X costs C, Y costs D"), every list item grammatically identical.
- Why: parallel structure is high-probability continuation — once one clause sets a template, the model completes it.
- Detect: highlight parallel constructions. Occasional parallelism is craft; wall-to-wall is generation.
- Counter: "Break parallel structure at least once per section. Let one item in any list be a different shape."

### 4. Voice tells

**No first-person stakes.**
- Tell: the author never appears, or appears only as a corporate "we". Nothing in the piece cost anyone time, money, or embarrassment. Nobody was wrong and then corrected.
- Why: assistants are trained to be nobody — helpful, neutral, and absent.
- Detect: search for "I". Then search for anything that went wrong. A piece where the author risked nothing and learned nothing was probably written by something that can't do either.
- Counter: "Write in first person. Include at least one moment where something surprised you, cost you time, or proved you wrong — a real one, with the detail that makes it checkable."

**No specific opinions — nothing risked.**
- Tell: every judgment is one the whole industry already agrees with ("reliability matters", "AI is powerful but must be used responsibly"). Nothing a competitor would bother disputing.
- Why: consensus is the safest token path.
- Detect: could a competitor publish this paragraph under their logo without edits? Then it says nothing.
- Counter: "State at least one opinion a reasonable person in the field would dispute, and defend it. Cut every sentence that could appear unchanged in any competitor's post."

**Fake enthusiasm.**
- Tell: "We're thrilled to announce", "excited to share", exclamation points about routine work, "amazing" things that are ordinary.
- Why: press-release register saturates the training data for announcement-shaped text.
- Detect: does the excitement have a stated reason? Enthusiasm without a wired-in cause is fake by construction.
- Counter: "Ban announcement register ('thrilled', 'excited', 'proud to share'). If something is genuinely good, show the number or the anecdote that makes it good and let the reader get excited."

**Sycophancy toward the reader.**
- Tell: "Great question." "You're absolutely right to wonder about this." Flattery as filler, agreement as reflex.
- Why: RLHF directly optimizes for making the reader feel good; Forbes lists sycophancy among the top 2026 giveaways.
- Detect: any sentence whose only function is to approve of the reader.
- Counter: "Never compliment or reassure the reader. Respect them by getting to the point."

**Uniform confidence — no uncertainty.**
- Tell: everything asserted with equal, total certainty. No "I think", "probably", "I'd guess", "we haven't tested this".
- Why: hedging on facts is trained out (rightly), but the model overshoots and stops flagging genuine unknowns.
- Detect: does the piece distinguish between what's measured and what's believed? If every claim has the same epistemic temperature, it's generated.
- Counter: "Mark uncertainty honestly: where the evidence is thin, say 'I'd guess' or 'we haven't measured this' — and make sure measured claims cite their measurement."

### 5. Content tells

**Generic examples.**
- Tell: "Imagine a small business owner named Sarah..." Hypothetical users, round numbers, examples that fit any product in the category.
- Why: the model has no experiences, so it interpolates a plausible one.
- Detect: is the example checkable? Does it have a date, a version number, a dollar amount, a name of a real thing? Generic examples survive being moved to a competitor's blog; real ones don't.
- Counter: "Every example must be real and checkable: a date, a number, a repo path, an error message. No invented personas. If you don't have a real example, make the claim without one."

**No lived detail.**
- Tell: descriptions of work with none of the texture of doing it — no dead ends, no "this took three tries", no specific tool that broke.
- Why: the model describes the concept of the work, not the experience.
- Detect: could this section have been written without doing the work? If yes, it reads that way.
- Counter: "Include one concrete lived detail per section — the actual command, the wrong first attempt, the run that failed and why. Pull them from the real logs/history, not imagination."

**Symmetric coverage of subtopics nobody asked about.**
- Tell: the survey reflex — every facet of the topic gets a dutiful paragraph, weighted equally, including ones irrelevant to the argument. Reads like a Wikipedia outline wearing a blog post.
- Why: coverage is safe; omission feels risky to a model that can't judge relevance from stakes it doesn't have.
- Detect: for each section ask "what breaks if this is cut?" If the answer is "nothing, but it'd be less complete" — cut it.
- Counter: "Cover only what serves the argument. Depth over coverage. Skip anything the reader can Google, and don't apologize for skipping it."

**Filler-context openers.**
- Tell: "In today's digital age, businesses increasingly rely on automation..." The first paragraph situates the topic in the broadest possible frame before saying anything.
- Why: it's the modal opening for the genre; pure preamble is zero-risk.
- Detect: delete the first paragraph. Better without it? (Almost always yes.)
- Counter: "Start inside the story: first sentence states a specific fact, number, or event unique to this piece. No scene-setting about the industry, the era, or the world."

---

## Cold email tells

AI-written sales email has its own recognizable shapes now. 61% of recipients
claim they can spot it, and the tells below are what they're spotting.

1. The mail-merge opener: "Hi {Name} — I noticed you {observation about their
   website}." The em dash after the name, then a compliment or observation
   that proves you ran a scraper. If you know something about their business,
   say it the way a colleague would: as shared knowledge, mid-thought, in
   natural word order. "Your team runs benefit checks the 271 never returns
   complete" beats "I noticed you offer verification of benefits services."
2. Batch parallelism. One AI email is hard to spot; thirty with identical
   sentence skeletons and a swapped noun are not. Burstiness applies across a
   campaign, not just inside one email. Vary the first sentence's grammatical
   shape from email to email. If every message could be diffed against the
   template and only the merge fields change, rewrite until that's false.
3. "Quick question" subjects, "Hope this finds you well," "I'll keep this
   brief" (then not being brief), "Does this resonate?", "Worth a chat?"
4. The contrast frame: "It's not about X — it's about Y." "We don't just
   automate; we verify." One of these can land. As a habit it's a signature.
5. Performative brevity: "No fluff." "Straight to the point." Saying it is
   the opposite of doing it.
6. The flattery bridge: "Impressive work on..." followed by a pivot to the
   pitch. Everyone knows the compliment was generated. If you can't praise
   something specific enough to survive a follow-up question on a call,
   don't praise at all.
7. Colons in subject lines and headline-ese ("Cut denials: a new approach").
   Humans writing to one person don't headline.

The test for an outreach email: could the recipient forward it to a colleague
with "do we know this guy?" and have the colleague answer "sounds like it."

## Pre-publish checklist

Scan before sending. Each hit is a rewrite prompt, not just a deletion.

- [ ] Any banned-list words or stock phrases? (grep)
- [ ] Any "it's not X — it's Y" scaffolds, or "not just" constructions?
- [ ] More than one em dash per ~150 words?
- [ ] Any three-item parallel list that didn't earn it?
- [ ] Shortest sentence over 10 words? (Nothing lands.)
- [ ] Paragraphs all the same size? Sections all the same length?
- [ ] Bullets doing argument's job? Bold-lead bullets restated?
- [ ] Section openers restating headers; a recap ending?
- [ ] Zero contractions? Zero fragments?
- [ ] Zero "I"? Zero uncertainty? Zero opinion anyone would dispute?
- [ ] Any example that's hypothetical or uncheckable?
- [ ] Any sentence a competitor could publish unchanged?
- [ ] Read a paragraph aloud: press release, or colleague over coffee?

More than two hits: rewrite, don't patch.

## Prompting agents to write human

What actually works, distilled from the 2026 discussion and our own use:

1. **Constrain structure, not just vocabulary.** Word bans get paraphrased around. Structural rules ("no lists of three", "one-sentence paragraph per page", "end on the last new thought") change how the text is built.
2. **Feed it real material.** An agent invents generic detail unless you hand it the real logs, numbers, dates, and failures. The counter to "no lived detail" is access to the lived detail.
3. **Demand stakes and opinion explicitly.** "First person; one thing that went wrong; one opinion a competitor would dispute, defended." Models won't risk anything unless instructed to.
4. **Two passes.** Draft for content, then a separate de-telling edit pass against the checklist. Asking for both at once degrades both.
5. **Give it a voice sample.** Two or three paragraphs of the actual author's writing beat any list of adjectives about tone.

A paste-able instruction block:

> Write in first person as [author]. Banned: delve, leverage, robust, seamless, crucial, pivotal, landscape, testament, comprehensive, harness, foster, streamline, empower, transformative, game-changer, "it's worth noting", "in today's...", announcement register ("thrilled", "excited to share"). No lists of exactly three parallel items. No "it's not X, it's Y" framing — state the claim and support it. At most one em dash per three paragraphs. Vary sentence length hard: some sentences under six words, at least one single-sentence paragraph; fragments allowed. Prose by default; bullets only for genuine enumerations, never bolded-lead-then-restated. First sentence of the piece and of each section must contain a specific fact — no scene-setting, no restating the header. End on the last new thought; no summary. Include per section one concrete, checkable detail from the source material (date, number, command, error). State one opinion a reasonable competitor would dispute and defend it. Mark real uncertainty ("I'd guess", "we haven't measured"). Include one moment where something went wrong or surprised the author. Before returning, delete every sentence that could appear unchanged in a competitor's post.

Then run the checklist on the output anyway. The model will comply with the letter of every rule and still occasionally produce the register; the read-aloud test catches what the rules miss.

## Sources

- PNAS 2025: "Do LLMs write like humans?" (pnas.org/doi/10.1073/pnas.2422455122)
- Wikipedia: "Signs of AI writing" (en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
- ACL 2025: "Why Does ChatGPT Delve So Much?" (aclanthology.org/2025.coling-main.426/)
- GPTZero on perplexity/burstiness (gptzero.me/news/perplexity-and-burstiness-what-is-it/)
- TechCrunch: "Best guide to spotting AI writing comes from Wikipedia" (2025)
- Pangram Labs: overused AI phrases (pangram.com/blog/walking-through-ai-phrases)
- Plagiarism Today: em dashes and AI detection (2025)
- Forbes, Feb 2026: "The 15 New Giveaway Signs of AI-Generated Content" (forbes.com/sites/jodiecook/2026/02/03/)
- Forbes, Mar 2026: "How To Avoid ChatGPT-Isms In Your Writing" (forbes.com/sites/aytekintank/2026/03/31/)
- Ruben Hassid: "It's not [X], it's [Y]." (ruben.substack.com/p/its-not-x-its-y)
- Hunting the Muse: "How to spot when writing is AI" (huntingthemuse.net/library/how-to-tell-if-writing-is-ai)
- MakeUseOf: "5 writing habits that make you sound like ChatGPT" (makeuseof.com/writing-habits-that-make-you-sound-like-chatgpt/)
- arXiv 2501.15654: frequent ChatGPT users are accurate detectors of AI text
