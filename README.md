# .NET Staff Engineer Guide Book — interview preparation with Anki cards

A practical guide for .NET Software Engineers who prepare for interviews — **as the candidate and as
the interviewer**. It is built from the Smartcat AI Toolkit engineering skills (code style, testing,
code review, diff coverage, security) and extends them with async, multithreading, ASP.NET Core and
the architectural patterns Smartcat uses.

Written in plain English for readers whose first language is not English: short sentences,
no idioms, every "what" comes with a "why".

## Chapters

| # | Chapter | Anki deck |
|---|---|---|
| 00 | [How to use this book (and how .NET interviews work)](book/00-introduction.md) | [00](anki/00-introduction.txt) |
| 01 | [C# and the .NET runtime](book/01-csharp-and-runtime.md) | [01](anki/01-csharp-and-runtime.txt) |
| 02 | [Code style and naming](book/02-code-style.md) | [02](anki/02-code-style.txt) |
| 03 | [Async and await in depth](book/03-async-await.md) | [03](anki/03-async-await.txt) |
| 04 | [Multithreading, concurrency and distributed locks](book/04-multithreading.md) | [04](anki/04-multithreading.txt) |
| 05 | [ASP.NET Core](book/05-aspnet-core.md) | [05](anki/05-aspnet-core.txt) |
| 06 | [Architectural patterns at Smartcat](book/06-smartcat-architecture.md) | [06](anki/06-smartcat-architecture.txt) |
| 07 | [Domain events, the Outbox pattern and Kafka](book/07-events-outbox-kafka.md) | [07](anki/07-events-outbox-kafka.txt) |
| 08 | [Background task processing](book/08-background-tasks.md) | [08](anki/08-background-tasks.txt) |
| 09 | [MongoDB models, indexes and safe migrations](book/09-mongodb-and-migrations.md) | [09](anki/09-mongodb-and-migrations.txt) |
| 10 | [Unit and integration testing](book/10-testing.md) | [10](anki/10-testing.txt) |
| 11 | [Diff coverage](book/11-diff-coverage.md) | [11](anki/11-diff-coverage.txt) |
| 12 | [Code review from both sides of the MR](book/12-code-review.md) | [12](anki/12-code-review.txt) |
| 13 | [Secure .NET code: OWASP in practice](book/13-security.md) | [13](anki/13-security.txt) |
| 14 | [The interview playbook](book/14-interview-playbook.md) | [14](anki/14-interview-playbook.txt) |

## Anki cards

Each chapter has its own deck file in `anki/`. `anki/all-chapters.txt` holds every card, with one
sub-deck per chapter (`DotNet Interview Guide::NN Title`).

**Import (Anki desktop 2.1.55 or newer):** File → Import → pick a `.txt` file → Import. The header
lines at the top of each file set the separator (tab), HTML, note type (Basic), deck and tags, so no
manual field mapping is needed. Re-importing the same file updates matching cards instead of
duplicating them (Anki matches on the first field).

**Other tools** (Mochi, RemNote, Obsidian Spaced Repetition, AnkiDroid/AnkiMobile via desktop sync):
the files are tab-separated values — column 1 Front, column 2 Back (HTML), column 3 tags, plus
column 4 deck in `all-chapters.txt`. Lines starting with `#` are headers.

**Useful tags:** `chNN` (chapter), `smartcat` (company-specific convention), `interviewer` (cards
that train the interviewer side). Example filtered deck search: `tag:interviewer tag:ch06`.

## Maintenance

```bash
python3 scripts/validate_anki.py anki/*.txt   # format check: 3 fields, escaped HTML, tags
python3 scripts/build_all.py                  # rebuild anki/all-chapters.txt
```

Writing rules for new chapters and cards: [STYLE.md](STYLE.md). Chapter plan: [OUTLINE.md](OUTLINE.md).
