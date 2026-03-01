# Writing That Doesn't Sound Like an LLM

A project-agnostic reference. Based on a literature review of AI detection research, Wikipedia's "Signs of AI Writing" page, and practical advice from 2024-2026.

## How detectors work

Two main signals:

Perplexity measures how predictable your word choices are. LLMs pick the statistically most likely next word, which makes their output low-perplexity. Human writing is messier. We use idioms, unexpected metaphors, sentence fragments. A perplexity score above 85 reads as more human (per GPTZero).

Burstiness measures variation in sentence length across a document. Humans write in bursts. A long winding sentence, then a short one. Then maybe three medium ones. LLMs produce sentences of roughly the same length, one after another, like a metronome.

## Words to ban

These words have been measured spiking 50%+ since ChatGPT launched. Using any of them is a strong AI signal.

delve, tapestry, landscape, realm, intricate, pivotal, crucial, underscore, foster, testament, nuanced, comprehensive, vibrant, robust, meticulous, leverage, harness, embark, beacon, enhance, furthermore, moreover, notably, arguably, subsequently, accordingly, consequently, indeed, significantly, paramount, multifaceted, holistic, seamless, cutting-edge, groundbreaking, transformative, unprecedented, innovative, revolutionary, game-changer, paradigm, synergy, empower, streamline, optimize, elevate, unleash, unlock, commendable, unparalleled, pioneering, versatile, adaptive, disruptive, reimagine, democratize, frictionless, showcasing, garner, accentuate, meticulously, align

Plain replacements:
- delve into -> look at, examine, dig into
- landscape -> field, area, world
- leverage -> use
- comprehensive -> thorough, full, complete
- pivotal/crucial -> key, important, big
- robust -> strong, solid
- foster -> build, grow, encourage
- enhance -> improve, boost
- harness -> use, put to work
- embark -> start, begin
- testament -> proof, sign, evidence
- intricate -> complex, detailed, tricky
- underscore -> show, point out (or just state the claim)
- nuanced -> subtle, complicated (or describe the actual nuance)
- seamless -> smooth, easy
- furthermore/moreover/additionally -> delete entirely, just start the next sentence

## Phrases to avoid

"It is important to note that" / "It is worth noting" / "A deeper understanding" / "In the ever-evolving landscape of" / "The complex interplay" / "No discussion would be complete without" / "Providing valuable insights into" / "Stands as a testament" / "Plays a vital role" / "Serves as a powerful" / "Unlock the potential of" / "Harness the power of" / "Embark on a journey" / "Pave the way for" / "Navigating the complexities of" / "In a world where..." / "Here's the kicker" / "And honestly? That's rare." / "Based on the information provided"

## Structural tells

1. Rule of three. LLMs love tripled constructions ("adjective, adjective, adjective" or "short phrase, short phrase, and short phrase"). If you catch yourself listing three things the same way, break the pattern.

2. Mechanical transitions. "On the other hand," "moreover," "furthermore," "however," "in contrast" between every paragraph. Humans just start the next thought.

3. Em dash overuse. ChatGPT uses an em dash roughly every 60-70 words. Use commas, parentheses, colons, or just cut the aside.

4. Bolded bullet titles restated. A bullet with a bold phrase immediately reworded in the sentence that follows. ("**Scalable architecture**: The architecture is designed to scale...")

5. Title-case headings everywhere. LLMs capitalize all main words. Humans often use sentence case.

6. Five-paragraph essay structure. Intro, three body paragraphs, conclusion. Real writing meanders.

7. The conclusion paragraph. If your last paragraph starts with "In conclusion," "In summary," "Overall," or "Ultimately," delete it. Just end when you're done.

8. Present participial clauses. LLMs use "ensuring," "highlighting," "emphasizing," "reflecting" at 2-5x the human rate. These add opinion without substance.

9. Nominalizations. "The utilization of" instead of "using." "The implementation of" instead of "we built." Turn nouns back into verbs.

## What humans do that LLMs don't

Vary sentence length wildly. Sometimes 8 words. Sometimes 35. LLMs cluster around 20-25.

Use contractions. Don't, can't, it's, won't, I've. LLMs avoid these.

Express uncertainty. "I think," "probably," "might," "I'm not sure but," "it seems like." LLM text sounds too certain about everything.

Include personal experience. "When I first tried this..." or "I remember..." or "Honestly, this part frustrated me." Even one line per section adds human signal.

Take a side. Make an argument. LLMs hedge and present both sides without committing.

Use humor or personality sparingly. A dry aside, understatement, mild self-deprecation. Not forced, just natural.

Reference concrete specifics. "Last Tuesday" not "recently." "After testing 47 approaches" not "after extensive testing." "The 3am debugging session" not "a challenging period."

Write messy paragraph structures. Not always parallel. Digress, circle back, follow a tangent.

Read it aloud. If it sounds like a press release, rewrite it. Aim for how you'd explain it to a colleague over coffee.

## Sources

- PNAS 2025: "Do LLMs write like humans?" (pnas.org/doi/10.1073/pnas.2422455122)
- Wikipedia: "Signs of AI writing" (en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing)
- ACL 2025: "Why Does ChatGPT Delve So Much?" (aclanthology.org/2025.coling-main.426/)
- GPTZero on perplexity/burstiness (gptzero.me/news/perplexity-and-burstiness-what-is-it/)
- TechCrunch: "Best guide to spotting AI writing comes from Wikipedia" (2025)
- Pangram Labs: overused AI phrases (pangram.com/blog/walking-through-ai-phrases)
- Plagiarism Today: em dashes and AI detection (2025)
