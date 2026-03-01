You're writing the first-ever automated status update for an open-source project's community channel. This is the inaugural post — people reading it may not know what the project does, why it matters, or what's been happening recently.

You'll receive:
1. Information about the project (what it is, what problem it solves, where it's headed)
2. Recent activity (commits, PRs, releases) showing what the team has been building

Your job is to write a post that:
- Opens with a brief, compelling explanation of what the project does and why someone should care
- Tells the story of where the project is right now — not just a list of changes, but the narrative arc
- Highlights 2-3 concrete things that happened recently that are exciting or meaningful
- Gives the reader a reason to stick around (what's coming next, how they can get involved)
- Ends with links or calls to action (join the community, try it out, contribute)

Rules:
- Don't start with "We're excited to announce" or "Hello everyone!" — jump straight into the substance
- Write like a person, not a press release. Casual but not sloppy.
- The reader should finish thinking "huh, that's interesting, I want to learn more"
- Don't try to explain every technical detail — focus on the "so what" for users
- Use concrete numbers and specifics when you can ("3 different AI models" not "multiple models")
- Keep it under 600 words for Discord
- Twitter version should hook someone who's never heard of the project
- Follow the writing guide strictly: no banned words, vary sentence length, use contractions

Format your response as JSON with these keys:
- "discord": The Discord introduction post (markdown, can include formatting)
- "twitter": The Twitter/X post (plain text, under 280 chars, include relevant hashtags)
- "summary": A one-line plain text summary
