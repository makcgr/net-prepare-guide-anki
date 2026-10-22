# Writing contract for this book (read fully before writing)

## Goal
A practical .NET Staff Engineer guide book that prepares a Software Engineer for .NET interviews
from BOTH sides: as the interviewee (what to know, how to answer) and as the interviewer (what to ask,
what a strong answer looks like, red flags). It is grounded in how Smartcat builds .NET services.

## Voice
- A friendly staff engineer explaining to a new senior colleague: peer-to-peer, down-to-earth,
  practical, honest about tradeoffs and uncertainty. Always explain the WHY, not only the WHAT.
- Written for readers whose first language is not English:
  - short sentences, one idea each, active voice;
  - NO idioms, phrasal verbs or slang ("fails", not "blows up"; "finish", not "wrap up");
  - no culture-dependent metaphors; plain words ("learn", not "internalize");
  - keep technical terms developers know (DI, diff, middleware); gloss any other term once at first use.
- Not dumbed-down. Assume strong fundamentals. Go deep where interviews go deep.
- A small amount of dry humor is fine, but never instead of substance.

## De-personify rule (MANDATORY)
The book and the cards are saved artifacts. They must contain **zero persona references**: no
"Steve", "Stiv", "Steve-style", "Staff Engineer's take", "Steviate", no first-person persona framing
("As your staff engineer, I..."). Use neutral labels: "Tip:", "Recommendation:", "In short:",
"Interviewer view:", "Common mistake:". Before finishing, run
`grep -niE 'steve|stiv|staff engineer|steviate' <your files>` and fix every hit.
(The phrase "Staff Engineer" is allowed ONLY in the book title in README.md.)

## Sources
- Primary: AI Toolkit skills in `/Users/mgr/work/ai-toolkit-private/capabilities/skills/<name>/SKILL.md`.
  Read every skill named in your assignment IN FULL before writing.
- Real code for examples (read-only, never edit): `/Users/mgr/work/smartcat` (monolith, `Features/*`),
  `/Users/mgr/work/project-tasks-service`, `/Users/mgr/work/work-orders-service`,
  `/Users/mgr/work/smartcat-ai-agents`, `/Users/mgr/work/filedisassembling`. Use them to make examples
  realistic. Do not paste secrets, connection strings, customer data, or internal hostnames.
- General .NET knowledge for the new chapters (async, threading, ASP.NET Core). Target .NET 8/10, C# 12+.
- Mark Smartcat-specific conventions clearly ("At Smartcat: ...") so the reader can tell company
  convention from general .NET truth. If you infer a convention from code and are not sure, say "likely".

## Chapter structure (every chapter)
1. `# NN. Title`
2. **Why this chapter matters** — 3–6 lines: what interviews test here and why it matters in real work.
3. **What you will be able to do** — 3–6 bullets (concrete outcomes).
4. Main sections (`##`), each with: concept → why → C# example (fenced ```csharp) → common mistake → tip.
   Prefer short, correct, compilable snippets. Show BAD vs GOOD when it helps.
5. **At Smartcat** — sections or callouts tying the topic to real Smartcat patterns, with file paths
   from the repos where useful (e.g. `smartcat/Features/Cat/...`).
6. **Interview corner** — two parts:
   - *As the interviewee*: 8–15 likely questions, each with "A strong answer covers:" bullets.
   - *As the interviewer*: what to ask, follow-up "depth probes", green flags, red flags, a short
     scoring rubric (e.g. Junior / Senior / Staff signals).
7. **Exercises** — 3–6 practical tasks (code to write, a bug to find, a design to explain), with
   short answer notes at the end of the chapter in a collapsible `<details>` block.
8. **Summary** — 5–10 bullet "remember this" points.
9. Footer line: `Anki deck: anki/NN-slug.txt`

Length guide: 600–1400 lines of Markdown per chapter. Depth over breadth, but cover the topic fully.
Use tables for comparisons, Mermaid diagrams (```mermaid) where a flow is easier to see than to read.

## Anki cards (write them in parallel with the chapter, one file per chapter)
File: `/Users/mgr/projects/.net-prepare-guide-anki/anki/NN-slug.txt`. Format is Anki's plain-text
import with file headers (Anki 2.1.55+; also readable by Mochi/RemNote/Obsidian-SR importers as TSV):

```
#separator:tab
#html:true
#notetype:Basic
#deck:DotNet Interview Guide::NN Title
#tags column:3
Front<TAB>Back<TAB>tag1 tag2
```

Rules (a validator enforces them — run it):
- Exactly 3 TAB-separated fields per line: Front, Back, Tags. No literal TAB or newline inside a field.
- Line breaks inside a field: `<br>`. Code: `<pre><code>...</code></pre>` with `<`, `>`, `&` escaped as
  `&lt;` `&gt;` `&amp;`. Inline code: `<code>...</code>`. Lists: `<ul><li>..</li></ul>` is fine.
- Never start a field with a double quote. Prefer `&quot;` for quotes anywhere.
- Tags: space-separated, lowercase, kebab-case, no spaces inside a tag. Always include `chNN` and a
  topic tag (e.g. `ch03 async configureawait`). Add `smartcat` for company-specific cards and
  `interviewer` for cards that train the interviewer side.
- 40–80 cards per chapter. One fact or idea per card (minimum-information principle). Front is a
  clear question; Back is the short answer first, then 1–3 lines of why/example.
- Mix: definitions, "why", "what is wrong with this code" (code on front), "compare X vs Y",
  "what happens when...", Smartcat conventions, and interviewer cards ("What follow-up tells a Senior
  from a Staff answer on X?").
- Validate: `python3 /Users/mgr/projects/.net-prepare-guide-anki/scripts/validate_anki.py anki/NN-slug.txt`
  must print `OK`. Fix and re-run until it does.

## File ownership
Write ONLY the files assigned to you. Do not edit README.md, STYLE.md, OUTLINE.md, or other chapters.
Cross-reference other chapters by number and title, e.g. "see chapter 03 (Async and await)".
