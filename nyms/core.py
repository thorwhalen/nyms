"""The facade: detect, pseudonymise, re-identify, check. One object, five seams.

::

    from nyms import Pseudonymiser
    p = Pseudonymiser('case-2026', names=['Rasmus Jensen'])
    result = p.pseudonymise(text)      # result.text goes to the AI; result.report says what happened
    answer = p.reidentify(ai_output)   # answer.text has the originals back; answer.unmatched lists invented tokens
    p.check(outgoing_text)             # originals that would leak, before anything is sent

The seams, each one keyword argument of :class:`Pseudonymiser`:

===========  =====================================================  ==========================================
seam         v1 default                                             replacement it allows
===========  =====================================================  ==========================================
detectors    :func:`nyms.detect.default_detectors` (regex, checksum, gazetteer)   a model-based second pass (spaCy/DaCy, GLiNER, an LLM via ``aix``/``creel``), a Presidio adapter
policy       :meth:`nyms.policy.Policy.default`                     ``Policy.strict()``, ``identifiers()``, a policy file
strategy     :class:`nyms.surrogates.Counter` (``[PERSON_1]``)      ``KeyedWords``, ``RandomWords``, ``Aliases``
store        ``dol.JsonFiles`` under ``~/.local/share/nyms/<project>/mapping``   any ``MutableMapping``; ``encrypt=True`` for Fernet at rest
key          :func:`nyms.keys.resolve_key` (env var, key file)      ``keyring``, ``config2py``, a passphrase
===========  =====================================================  ==========================================

Not seams, written directly on purpose: the span data model, the overlap rule's signature,
the report's shape, the bracket-tolerant re-identification matcher.

>>> p = Pseudonymiser(store={})
>>> r = p.pseudonymise("Rasmus Jensen (CPR 010190-1234) skylder 12.500 kr. Rasmus Jensens advokat ringede.")
>>> r.text
'[PERSON_1] (CPR [CPR_1]) skylder [AMOUNT_1]. [PERSON_1]s advokat ringede.'
>>> p.reidentify("Svar: [PERSON_1] skal betale [AMOUNT_1]. [person 1]s sag.").text
'Svar: Rasmus Jensen skal betale 12.500 kr. Rasmus Jensens sag.'
>>> p.check("Rasmus Jensen bor her")
['Rasmus Jensen']
"""

from __future__ import annotations

import re
from collections.abc import Iterable, MutableMapping
from dataclasses import dataclass, field
from functools import cached_property

from nyms.detect import Detector, default_detectors, detect, detect_raw, known_values_detectors
from nyms.keys import resolve_key
from nyms.mapping import MappingStore, encrypted, local_mapping_store, normalise
from nyms.policy import Policy
from nyms.spans import Span, apply_replacements, resolve_overlaps
from nyms.surrogates import Counter, Strategy

CAVEAT = (
    "Pseudonymised, not anonymous: the mapping store and key re-identify everything replaced; "
    "a deterministic pass catches patterns and listed names, not unlisted names, roles, rare "
    "events or context that identifies without an identifier."
)


@dataclass
class Result:
    """What :meth:`Pseudonymiser.pseudonymise` returns."""

    text: str
    replaced: list[Span]
    kept: list[Span]
    replacements: list[tuple[Span, str]]
    report: dict = field(default_factory=dict)

    @property
    def mapping(self) -> dict[str, str]:
        """``{surrogate: original}`` for this run only. Sensitive."""
        return {sur: span.text for span, sur in self.replacements}


@dataclass
class Reidentified:
    """What :meth:`Pseudonymiser.reidentify` returns."""

    text: str
    restored: int
    unmatched: list[str]


class Pseudonymiser:
    """The facade. See the module docstring for the seams."""

    def __init__(
        self,
        project: str = "default",
        *,
        detectors: Iterable[Detector] | None = None,
        policy: Policy | None = None,
        strategy: Strategy | None = None,
        store: MutableMapping[str, dict] | None = None,
        key: bytes | None = None,
        names: Iterable[str] = (),
        rootdir=None,
        encrypt: bool = False,
        prefilter: bool = False,
    ):
        self.project = project
        self.policy = Policy.default() if policy is None else policy
        self._key = key
        self.detectors = list(default_detectors(names=names) if detectors is None else detectors)
        if prefilter:
            self.detectors = self.policy.detector_filter(self.detectors)
        if store is None:
            codec = encrypted(self.key) if encrypt else None
            store = local_mapping_store(project, rootdir=rootdir, codec=codec)
        self.mapping = MappingStore(store, strategy=Counter() if strategy is None else strategy)

    @cached_property
    def key(self) -> bytes:
        return self._key if self._key is not None else resolve_key(self.project)

    # -- the four verbs -------------------------------------------------------
    def detect(self, text: str) -> list[Span]:
        return detect(text, self.detectors)

    def pseudonymise(self, text: str) -> Result:
        # Two passes. The first finds what the detectors and the policy agree on and enters
        # the new values into the mapping. The second adds a detector for every value the
        # project already knows, so an occurrence a heuristic scored too low (a name at the
        # start of a sentence, a company in a heading) is still replaced once the same value
        # was accepted anywhere, in this document or an earlier one.
        replaced, kept = self._decide(text, self.detectors)
        for s in replaced:
            self.mapping.resolve(s.entity_type, s.text)
        replaced, kept = self._decide(text, self.detectors + known_values_detectors(self.mapping))
        replacements = []
        for s in replaced:
            surrogate, suffix = self.mapping.resolve(s.entity_type, s.text)
            replacements.append((s, surrogate + suffix))
        new_text = apply_replacements(text, replacements)
        return Result(new_text, replaced, kept, replacements, self._report(replaced, kept))

    def _decide(self, text: str, detectors: list[Detector]) -> tuple[list[Span], list[Span]]:
        """Resolve overlaps over every detector's spans, then let the policy split them."""
        return self.policy.split(resolve_overlaps(detect_raw(text, detectors)))

    def reidentify(self, text: str) -> Reidentified:
        canon_to_original = {_canon(r.surrogate): r.original for r in self.mapping.records()}
        if not canon_to_original:
            return Reidentified(text, 0, _leftover_tokens(text))
        pattern = _tolerant_pattern(canon_to_original)
        count = 0

        def sub(m: re.Match) -> str:
            nonlocal count
            original = canon_to_original.get(_canon(m.group(0)))
            if original is None:
                return m.group(0)
            count += 1
            return original

        restored = pattern.sub(sub, text)
        return Reidentified(restored, count, _leftover_tokens(restored))

    def check(self, text: str) -> list[str]:
        """Originals from the mapping that occur in *text*: what would leak if it were sent."""
        found = []
        for rec in self.mapping.records():
            if _contains_value(text, rec.entity_type, rec.original):
                found.append(rec.original)
        return found

    # -- reporting ------------------------------------------------------------
    def _report(self, replaced: list[Span], kept: list[Span]) -> dict:
        by_type: dict[str, int] = {}
        by_detector: dict[str, int] = {}
        for s in replaced:
            by_type[s.entity_type] = by_type.get(s.entity_type, 0) + 1
            by_detector[s.detector] = by_detector.get(s.detector, 0) + 1
        return {
            "project": self.project,
            "policy": self.policy.name,
            "replaced": len(replaced),
            "replaced_by_type": dict(sorted(by_type.items())),
            "replaced_by_detector": dict(sorted(by_detector.items())),
            "kept": [{"entity_type": s.entity_type, "text": s.text, "score": s.score, "detector": s.detector} for s in kept],
            "distinct_values_in_project": len(self.mapping),
            "detectors_run": sorted({d.name for d in self.detectors}),
            "caveat": CAVEAT,
        }


# --------------------------------------------------------------------------- matching helpers

_TOKEN_RE = re.compile(r"\[\s*[A-Z][A-Z_]*\s*[_:\-\s]\s*[\w\-]+\s*\]")


def _canon(s: str) -> str:
    """``[ PERSON 1 ]`` -> ``person_1``; ``Alder  Brook`` -> ``alder_brook``."""
    s = s.strip().strip("[]").casefold()
    return re.sub(r"[\s_\-]+", "_", s).strip("_")


def _tolerant_pattern(canon_to_original: dict[str, str]) -> re.Pattern:
    """One alternation matching every surrogate with optional brackets, loose separators, any case."""
    alts = []
    for canon in sorted(canon_to_original, key=len, reverse=True):
        parts = [re.escape(p) for p in canon.split("_")]
        body = r"[\s_\-]*".join(parts)
        # With a closing bracket anything may follow (a genitive "s"); without one, a word
        # boundary is required so that PERSON_1 never matches inside PERSON_11.
        alts.append(rf"\[\s*{body}\s*\]|\[?\s*{body}(?![\w])")
    return re.compile(r"(?<![\w])(?:" + "|".join(alts) + r")", re.IGNORECASE)


def _leftover_tokens(text: str) -> list[str]:
    """Bracketed typed tokens still in *text*: ones the model invented or we never issued."""
    return sorted({m.group(0) for m in _TOKEN_RE.finditer(text)})


def _contains_value(text: str, entity_type: str, original: str) -> bool:
    norm = normalise(entity_type, original)
    if not norm:
        return False
    return norm in normalise(entity_type, text) or original in text
