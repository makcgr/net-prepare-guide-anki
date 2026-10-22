#!/usr/bin/env python3
"""Validate Anki plain-text import files used by this book. Prints OK or a list of problems."""
import re
import sys
from pathlib import Path

REQUIRED_HEADERS = ["#separator:tab", "#html:true", "#notetype:Basic", "#tags column:3"]
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def validate(path: Path) -> list[str]:
    problems = []
    lines = path.read_text(encoding="utf-8").split("\n")
    headers = [line for line in lines if line.startswith("#")]
    for required in REQUIRED_HEADERS:
        if required not in headers:
            problems.append(f"missing header {required!r}")
    if not any(h.startswith(("#deck:", "#deck column:")) for h in headers):
        problems.append("missing #deck: header")

    deck_column = any(h.startswith("#deck column:") for h in headers)
    expected_fields = 4 if deck_column else 3
    fronts = set()
    cards = 0
    for number, line in enumerate(lines, 1):
        if not line or line.startswith("#"):
            continue
        cards += 1
        fields = line.split("\t")
        if len(fields) != expected_fields:
            problems.append(f"line {number}: expected {expected_fields} fields, got {len(fields)}")
            continue
        front, back, tags = fields[:3]
        if not front.strip() or not back.strip():
            problems.append(f"line {number}: empty front or back")
        for name, value in (("front", front), ("back", back)):
            if value.startswith('"'):
                problems.append(f"line {number}: {name} starts with a double quote")
            if value.count("<pre>") != value.count("</pre>"):
                problems.append(f"line {number}: unbalanced <pre> in {name}")
            if value.count("<code>") != value.count("</code>"):
                problems.append(f"line {number}: unbalanced <code> in {name}")
            if re.search(r"<(?!/?(pre|code|br|b|i|ul|ol|li|em|strong|table|tr|td|th|sub|sup|span|small)\b)[^>]*>", value):
                problems.append(f"line {number}: unescaped '<' or unknown tag in {name}")
        tag_list = tags.split()
        if not tag_list:
            problems.append(f"line {number}: no tags")
        for tag in tag_list:
            if not TAG_RE.match(tag):
                problems.append(f"line {number}: bad tag {tag!r}")
        if front in fronts:
            problems.append(f"line {number}: duplicate front")
        fronts.add(front)
    if cards == 0:
        problems.append("no cards")
    return problems


def main() -> int:
    exit_code = 0
    for arg in sys.argv[1:]:
        path = Path(arg)
        problems = validate(path)
        if problems:
            exit_code = 1
            print(f"{path}: {len(problems)} problem(s)")
            for problem in problems[:50]:
                print(f"  - {problem}")
        else:
            cards = sum(1 for l in path.read_text(encoding="utf-8").split("\n") if l and not l.startswith("#"))
            print(f"{path}: OK ({cards} cards)")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
