"""Deterministic word-level text comparison (no model involved)."""

import re
from difflib import SequenceMatcher

_TOKEN = re.compile(r"\S+\s*")


def _tokens(text):
    """Words, each carrying the whitespace that follows it.

    Leading whitespace (if any) is attached to the first word so that no
    original characters are lost.
    """
    stripped = text.lstrip()
    lead = text[: len(text) - len(stripped)]
    tokens = _TOKEN.findall(stripped)
    if tokens:
        tokens[0] = lead + tokens[0]
    return tokens


def word_diff(earlier, current):
    """Compare two excerpts word by word.

    Words are matched ignoring surrounding whitespace, but the original text of
    each word (and its trailing whitespace, including line breaks) is kept.
    Returns {"segments": [{"op": "equal|remove|add", "text": str}], "summary": {...}}.
    "equal" and "remove" text comes from the earlier excerpt; "add" text comes
    from the current excerpt.
    """
    a, b = _tokens(earlier), _tokens(current)
    matcher = SequenceMatcher(None, [t.strip() for t in a], [t.strip() for t in b],
                              autojunk=False)
    segments = []

    def push(op, text):
        if not text:
            return
        if segments and segments[-1]["op"] == op:
            segments[-1]["text"] += text
        else:
            segments.append({"op": op, "text": text})

    removed = added = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            push("equal", "".join(a[i1:i2]))
        else:
            if i2 > i1:
                push("remove", "".join(a[i1:i2]))
                removed += i2 - i1
            if j2 > j1:
                push("add", "".join(b[j1:j2]))
                added += j2 - j1
    return {
        "segments": segments,
        "summary": {
            "changed": bool(removed or added),
            "removed_words": removed,
            "added_words": added,
        },
    }
