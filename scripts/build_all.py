#!/usr/bin/env python3
"""Merge anki/NN-*.txt into anki/all-chapters.txt, keeping each chapter's deck via a deck column."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANKI = ROOT / "anki"
OUT = ANKI / "all-chapters.txt"

rows = []
for path in sorted(ANKI.glob("[0-9][0-9]-*.txt")):
    lines = path.read_text(encoding="utf-8").split("\n")
    deck = next(l.split(":", 1)[1] for l in lines if l.startswith("#deck:"))
    rows += [f"{l}\t{deck}" for l in lines if l and not l.startswith("#")]

header = ["#separator:tab", "#html:true", "#notetype:Basic", "#tags column:3", "#deck column:4"]
OUT.write_text("\n".join(header + rows) + "\n", encoding="utf-8")
print(f"{OUT}: {len(rows)} cards")
