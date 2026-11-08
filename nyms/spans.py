"""Spans: where a detector found something, and how findings are merged and applied.

A :class:`Span` is a half-open character interval ``[start, end)`` over the text as given
(Python ``str`` indexing, so code points, never bytes or tokens), with the entity type the
detector assigned, the matched text, a confidence score in ``[0, 1]`` and the detector's
name. Spans from several detectors overlap, and :func:`resolve_overlaps` decides which
survive: the longer span first, then the higher score, then the earlier one. That order is
a function so it can be tested and replaced.

>>> a = Span(0, 5, 'PERSON', 'Hans ', 0.5, 'heuristic')
>>> b = Span(0, 11, 'PERSON', 'Hans Jensen', 0.9, 'gazetteer')
>>> [s.detector for s in resolve_overlaps([a, b])]
['gazetteer']
>>> apply_replacements('Hans Jensen bor her', [(b, '[PERSON_1]')])
'[PERSON_1] bor her'
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Span:
    """One detected occurrence of an entity in a text."""

    start: int
    end: int
    entity_type: str
    text: str
    score: float = 1.0
    detector: str = ""

    @property
    def length(self) -> int:
        return self.end - self.start

    def overlaps(self, other: Span) -> bool:
        return self.start < other.end and other.start < self.end

    def to_dict(self) -> dict:
        return asdict(self)


#: Below this score a span is "weak": it never outranks an overlapping strong span, however long.
WEAK_SCORE = 0.6


def default_priority(span: Span) -> tuple:
    """Sort key: strong spans before weak ones, then longer, then higher score, then earlier.

    A long, low-confidence heuristic match must not swallow a short, certain one (a gazetteer
    name inside a capitalised phrase); among spans of the same strength, the longer wins
    (an address over the postcode inside it), then the score (a date over a phone number of
    the same length).
    """
    return (span.score < WEAK_SCORE, -span.length, -span.score, span.start)


def resolve_overlaps(
    spans: Iterable[Span], *, priority: Callable[[Span], tuple] = default_priority
) -> list[Span]:
    """Keep a non-overlapping subset of *spans*, best first by *priority*, in text order.

    >>> s = [Span(0, 4, 'A', 'aaaa', 0.5), Span(2, 6, 'B', 'bbbb', 0.9), Span(8, 9, 'C', 'c')]
    >>> [x.entity_type for x in resolve_overlaps(s)]
    ['B', 'C']
    """
    chosen: list[Span] = []
    for span in sorted(spans, key=priority):
        if not any(span.overlaps(c) for c in chosen):
            chosen.append(span)
    return sorted(chosen, key=lambda s: s.start)


def apply_replacements(text: str, replacements: Iterable[tuple[Span, str]]) -> str:
    """Rebuild *text* with each span replaced by its string. Spans must not overlap.

    >>> apply_replacements('a b c', [(Span(2, 3, 'X', 'b'), 'B')])
    'a B c'
    """
    out: list[str] = []
    pos = 0
    for span, new in sorted(replacements, key=lambda t: t[0].start):
        if span.start < pos:
            raise ValueError(f"overlapping replacement at {span.start}")
        out.append(text[pos : span.start])
        out.append(new)
        pos = span.end
    out.append(text[pos:])
    return "".join(out)
