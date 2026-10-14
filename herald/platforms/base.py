"""Base class for platform publishers."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

ELLIPSIS = "\u2026"
_WORD_BREAK = re.compile(r"\s+")
_TRAILING = " \t\r\n,;:"


def shorten(
    text: str,
    limit: int,
    measure: Callable[[str], int] = len,
    suffix: str = ELLIPSIS,
) -> str:
    """Return text unchanged if it fits, else cut it at a word boundary and add suffix.

    ``measure`` gives the length the platform counts, such as X's weighted
    length. Only a text with no word boundary that fits is cut inside a word.
    """
    if measure(text) <= limit:
        return text

    def cut(end: int) -> str:
        return text[:end].rstrip(_TRAILING) + suffix

    def longest(ends: list[int]) -> str | None:
        # Longer cuts never measure shorter, so search for the last one that fits.
        best, low, high = None, 0, len(ends) - 1
        while low <= high:
            middle = (low + high) // 2
            candidate = cut(ends[middle])
            if measure(candidate) <= limit:
                best, low = candidate, middle + 1
            else:
                high = middle - 1
        return best

    word_ends = [m.start() for m in _WORD_BREAK.finditer(text) if text[: m.start()].strip()]
    return longest(word_ends) or longest(list(range(1, len(text)))) or ""


@dataclass
class PublishResult:
    platform: str
    success: bool
    message: str = ""
    url: str = ""


class Publisher(ABC):
    """Abstract base for posting content to a platform."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        ...

    @abstractmethod
    def publish(self, content: str, **kwargs) -> PublishResult:
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        ...
