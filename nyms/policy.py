"""The sensitivity policy: which detected spans get replaced, which are kept and reported.

A :class:`Policy` is evaluated **after** detection (all detectors run, the policy decides),
which is what lets the run report say what it saw and chose to keep. A policy can also be
applied **before** detection through :meth:`Policy.detector_filter`, to skip detectors whose
type it will never act on; both orders are supported because the user asked for both.

Three presets:

- :meth:`Policy.default`: tiers 0 and 1, plus organisation identifiers and amounts; dates,
  postcodes and URLs are kept and reported.
- :meth:`Policy.identifiers`: tiers 0 and 1 only.
- :meth:`Policy.strict`: everything detected.

Allow and deny lists are matched on the span text, case-insensitively: ``allow`` is never
replaced (a public institution's name, say), ``deny`` is always replaced (the parties'
names, which no detector may know). A policy is a plain dataclass, so it serialises to and
from a dict (:meth:`to_dict`, :meth:`from_dict`) and can live in a project file.

>>> from nyms.spans import Span
>>> p = Policy.default()
>>> p.accepts(Span(0, 10, 'CPR', '010190-1234', 0.9))
True
>>> p.accepts(Span(0, 10, 'DATE', '01.01.1990', 0.9))
False
>>> Policy.strict().accepts(Span(0, 10, 'DATE', '01.01.1990', 0.9))
True
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, asdict

from nyms.spans import Span
from nyms.taxonomy import ENTITY_TYPES, tier_of

DEFAULT_MIN_SCORE = 0.5
_ALWAYS_TIERS = (0, 1)
_DEFAULT_EXTRA_TYPES = ("CVR", "ORG", "AMOUNT")


@dataclass
class Policy:
    """What to do with detected spans. See the module docstring."""

    name: str = "default"
    include: frozenset[str] | None = None  # None: every type not excluded
    exclude: frozenset[str] = frozenset()
    min_score: float = DEFAULT_MIN_SCORE
    min_score_by_type: dict[str, float] = field(default_factory=dict)
    allow: frozenset[str] = frozenset()  # never replaced (span text, casefolded)
    deny: frozenset[str] = frozenset()  # always replaced
    keep: Callable[[Span], bool] | None = None  # extra post-detection veto hook

    # -- presets -------------------------------------------------------------
    @classmethod
    def default(cls, **changes) -> Policy:
        types = {n for n, t in ENTITY_TYPES.items() if t.tier in _ALWAYS_TIERS}
        types.update(_DEFAULT_EXTRA_TYPES)
        return cls(name="default", include=frozenset(types), **changes)

    @classmethod
    def identifiers(cls, **changes) -> Policy:
        types = {n for n, t in ENTITY_TYPES.items() if t.tier in _ALWAYS_TIERS}
        return cls(name="identifiers", include=frozenset(types), **changes)

    @classmethod
    def strict(cls, **changes) -> Policy:
        return cls(name="strict", include=None, min_score=0.0, **changes)

    # -- evaluation ----------------------------------------------------------
    def wants(self, entity_type: str) -> bool:
        """Whether this policy acts on a type at all (pre-detection filter)."""
        if entity_type in self.exclude:
            return False
        if self.include is None:
            return True
        return entity_type in self.include or tier_of(entity_type) == 0

    def detector_filter(self, detectors: Iterable) -> list:
        """The detectors whose entity type this policy wants; a pre-detection filter."""
        return [d for d in detectors if self.wants(d.entity_type)]

    def accepts(self, span: Span) -> bool:
        """Whether *span* gets replaced under this policy (post-detection decision)."""
        key = span.text.casefold().strip()
        if key in self.allow:
            return False
        if key in self.deny:
            return True
        if not self.wants(span.entity_type):
            return False
        threshold = self.min_score_by_type.get(span.entity_type, self.min_score)
        if span.score < threshold:
            return False
        if self.keep is not None and not self.keep(span):
            return False
        return True

    def split(self, spans: Iterable[Span]) -> tuple[list[Span], list[Span]]:
        """``(replaced, kept)`` under this policy."""
        replaced, kept = [], []
        for s in spans:
            (replaced if self.accepts(s) else kept).append(s)
        return replaced, kept

    # -- serialisation -------------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("keep")
        for k in ("include", "exclude", "allow", "deny"):
            d[k] = sorted(d[k]) if d[k] is not None else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Policy:
        d = dict(d)
        for k in ("include", "exclude", "allow", "deny"):
            if d.get(k) is not None:
                d[k] = frozenset(d[k])
        return cls(**d)

    def with_names(self, *names: str) -> Policy:
        """A copy whose deny list also holds *names* (casefolded): the parties you know.

        >>> p = Policy.default().with_names('Acme ApS')
        >>> 'acme aps' in p.deny
        True
        """
        return Policy(**{**asdict(self), "deny": self.deny | {n.casefold().strip() for n in names}})
