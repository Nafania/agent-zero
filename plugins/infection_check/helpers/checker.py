import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent import Agent


_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous\s+instructions",
    r"you\s+are\s+now\s+a\s+different\s+ai",
    r"new\s+system\s+prompt",
    r"override\s+system\s+prompt",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def check_for_injection(text: str) -> list[str]:
    """Return list of matched injection patterns found in text."""
    matches = []
    for pattern in _COMPILED:
        if pattern.search(text):
            matches.append(pattern.pattern)
    return matches


def is_safe(text: str) -> bool:
    """Return True if no injection patterns found."""
    return len(check_for_injection(text)) == 0
