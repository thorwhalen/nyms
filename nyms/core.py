"""The facade: detect, pseudonymise, re-identify, check. One object, six seams.

::

    from nyms import Pseudonymiser
    p = Pseudonymiser('case-2026', names=['Rasmus Jensen'])
    result = p.pseudonymise(text)      # result.text goes to the AI; result.report says what happened
    answer = p.reidentify(ai_output)   # answer.text has the originals back; answer.unmatched lists invented tokens
    p.check(outgoing_text)             # originals that would leak, before anything is sent

The seams, each one keyword argument of :class:`Pseudonymiser`:

==============  =====================================================  ==========================================
seam            v1 default (no new dependency)                         replacement it allows
==============  =====================================================  ==========================================
detectors       :func:`nyms.detect.default_detectors` (regex, checksum, gazetteer)   any callable ``text -> spans``; a Presidio adapter
post_detectors  none                                                   the model-based second pass (spaCy/DaCy, GLiNER, an LLM via ``aix``/``creel``), run on the already-pseudonymised text
policy          :meth:`nyms.policy.Policy.default`                     ``Policy.strict()``, ``identifiers()``, a policy file
strategy        :class:`nyms.surrogates.Counter` (``[PERSON_1]``)      ``KeyedWords``, ``RandomWords``, ``Aliases``
store           ``dol`` files under ``~/.local/share/nyms/<project>/mapping``   any ``MutableMapping``; ``encrypt=True`` for Fernet at rest
key             :func:`nyms.keys.resolve_key` (env var, key file)      ``keyring``, ``config2py``, a passphrase
==============  =====================================================  ==========================================

Not seams, written directly on purpose: the span data model, the report's shape, the
tolerant re-identification matcher, the order of the stages.

How a run works. The text is NFC-normalised. Stage 1: every detector's spans, overlap
resolution (strong spans before weak, longer before shorter), the policy's split into
replaced and kept; an accepted span nested inside a kept one (a CPR number inside a URL the
policy keeps) is still replaced. New values enter the mapping, and a second pass adds
detectors for everything the project knows (its values, name components, its own surrogates)
so every occurrence is consistent. Stage 2, when ``post_detectors`` are given: they run on the
pseudonymised text, where the surrogates are protected from re-detection, and what they find
is replaced and added to the mapping too.

>>> p = Pseudonymiser(store={})
>>> r = p.pseudonymise("Rasmus Jensen (CPR 010190-1234) skylder 12.500 kr. Rasmus Jensens advokat ringede.")
>>> r.text
'[PERSON_1] (CPR [CPR_1]) skylder [AMOUNT_1]. [PERSON_1]s advokat ringede.'
>>> p.reidentify("Svar: [PERSON_1] skal betale [AMOUNT_1]. [person 1]s sag.").text
'Svar: Rasmus Jensen skal betale 12.500 kr. Rasmus Jensens sag.'
>>> p.check("Rasmus Jensen bor her")
['Rasmus Jensen']
>>> p.pseudonymise(r.text).text == r.text   # idempotent: surrogates are never re-detected
True
"""

from __future__ import annotations

import re
from collections.abc import Iterable, MutableMapping
from dataclasses import dataclass, field
from functools import cached_property

from nyms.detect import (
    DetectorLike,
    default_detectors,
    detect,
    detect_raw,
    detector_name,
    known_values_detectors,
    normalise_text,
)
from nyms.keys import resolve_key
from nyms.mapping import MappingStore, canon, encrypted, local_mapping_store, normalise
from nyms.policy import Policy
from nyms.spans import Span, apply_replacements, resolve_overlaps
from nyms.surrogates import Counter, Strategy
from nyms.taxonomy import SURROGATE_TYPE, tier_of

CAVEAT = (
    "Pseudonymised, not anonymous: the mapping store and key re-identify everything replaced; "
    "a deterministic pass catches patterns and listed names, not unlisted names, roles, rare "
    "events or context that identifies without an identifier."
)


@dataclass
class Result:
    """What :meth:`Pseudonymiser.pseudonymise` returns. Spans refer to the NFC-normalised input."""

    text: str
    replaced: list[Span]
    kept: list[Span]
    replacements: list[tuple[Span, str]]
    report: dict = field(default_factory=dict)
    #: Stage-2 replacements (``post_detectors``), with offsets in the stage-1 output.
    post_replacements: list[tuple[Span, str]] = field(default_factory=list)

    @property
    def mapping(self) -> dict[str, str]:
        """``{surrogate: original}`` for this run only. Sensitive."""
        return {
            sur: span.text
            for span, sur in [*self.replacements, *self.post_replacements]
        }


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
        detectors: Iterable[DetectorLike] | None = None,
        post_detectors: Iterable[DetectorLike] = (),
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
        self.names = [n for n in names if n and n.strip()]
        self.detectors = list(
            default_detectors(names=self.names) if detectors is None else detectors
        )
        self.post_detectors = list(post_detectors)
        if prefilter:
            self.detectors = self.policy.detector_filter(self.detectors)
        if store is None:
            codec = encrypted(self.key) if encrypt else None
            store = local_mapping_store(project, rootdir=rootdir, codec=codec)
        self.mapping = MappingStore(
            store, strategy=Counter() if strategy is None else strategy
        )

    @cached_property
    def key(self) -> bytes:
        return self._key if self._key is not None else resolve_key(self.project)

    # -- the four verbs -------------------------------------------------------
    def detect(self, text: str) -> list[Span]:
        return detect(normalise_text(text), self.detectors)

    def pseudonymise(self, text: str) -> Result:
        text = normalise_text(text)
        # Pass 1: the detectors plus what the project already knows (its values, the name
        # components of the known parties, its own surrogates); new values enter the mapping.
        known = known_values_detectors(self.mapping, extra_names=self.names)
        replaced, _ = self._decide(text, self.detectors + known)
        for s in replaced:
            self.mapping.resolve(s.entity_type, s.value or s.text)
        # Pass 2: the same, now knowing this document's new values, so every occurrence is
        # consistent; a span pass 1 attributed to a real detector keeps that attribution.
        first = {(s.start, s.end): s for s in replaced}
        replaced, kept = self._decide(
            text,
            self.detectors
            + known_values_detectors(self.mapping, extra_names=self.names),
        )
        replaced = [
            first.get((s.start, s.end), s) if s.detector == "known_values" else s
            for s in replaced
        ]
        replacements = self._replacements(replaced)
        out = apply_replacements(text, replacements)
        # Stage 2: detectors that run on the pseudonymised text (the model pass seam).
        post_replacements: list[tuple[Span, str]] = []
        if self.post_detectors:
            protect = known_values_detectors(self.mapping)
            post_replaced, post_kept = self._decide(
                out, list(self.post_detectors) + protect
            )
            post_replaced = [s for s in post_replaced if s.detector != "known_values"]
            post_replacements = self._replacements(post_replaced)
            out = apply_replacements(out, post_replacements)
            kept = kept + [
                k for k in post_kept if k.detector not in ("known_values", "surrogates")
            ]
        return Result(
            out,
            replaced,
            kept,
            replacements,
            self._report(replaced, kept, post_replacements),
            post_replacements,
        )

    def _replacements(self, spans: list[Span]) -> list[tuple[Span, str]]:
        out = []
        for s in spans:
            # A span with a value stands for a known name; its text excludes any genitive by
            # construction (the gazetteer leaves the "s" outside the span), so no suffix.
            surrogate, suffix = self.mapping.resolve(s.entity_type, s.value or s.text)
            out.append((s, surrogate + ("" if s.value else suffix)))
        return out

    def _decide(
        self, text: str, detectors: list[DetectorLike]
    ) -> tuple[list[Span], list[Span]]:
        """Resolve overlaps over every detector's spans, let the policy split them, then promote
        accepted spans nested inside kept ones (an identifier inside a kept URL)."""
        raw = detect_raw(text, detectors)
        winners = resolve_overlaps(raw)
        accepted, rejected = self.policy.split(
            w for w in winners if w.entity_type != SURROGATE_TYPE
        )
        for k in rejected:
            inner = [
                s
                for s in raw
                if _promotable(s)
                and k.contains(s)
                and s.length < k.length
                and self.policy.accepts(s)
            ]
            accepted.extend(resolve_overlaps(inner))
        accepted = resolve_overlaps(accepted)
        kept = [k for k in rejected if not any(a.contains(k) for a in accepted)]
        return accepted, kept

    def reidentify(self, text: str) -> Reidentified:
        records = list(self.mapping.records())
        if not records:
            return Reidentified(text, 0, _leftover_tokens(text))
        by_canon = {canon(r.surrogate): r.original for r in records}
        exact = {r.surrogate: r.original for r in records}
        pattern = _tolerant_pattern([r.surrogate for r in records])
        count = 0

        def sub(m: re.Match) -> str:
            nonlocal count
            hit = m.group(0)
            original = (
                exact.get(hit) if not hit.startswith("[") else by_canon.get(canon(hit))
            )
            if original is None:
                original = (
                    by_canon.get(canon(hit))
                    if hit.startswith("[") or _looks_bracketed(hit)
                    else None
                )
            if original is None:
                return hit
            count += 1
            return original

        restored = pattern.sub(sub, text)
        return Reidentified(restored, count, _leftover_tokens(restored))

    def check(self, text: str) -> list[str]:
        """Originals from the mapping that occur in *text*: what would leak if it were sent."""
        text = normalise_text(text)
        return [
            rec.original
            for rec in self.mapping.records()
            if _contains_value(text, rec.entity_type, rec.original)
        ]

    # -- reporting ------------------------------------------------------------
    def _report(
        self, replaced: list[Span], kept: list[Span], post: list[tuple[Span, str]]
    ) -> dict:
        by_type: dict[str, int] = {}
        by_detector: dict[str, int] = {}
        for s in [*replaced, *(s for s, _ in post)]:
            by_type[s.entity_type] = by_type.get(s.entity_type, 0) + 1
            by_detector[s.detector] = by_detector.get(s.detector, 0) + 1
        return {
            "project": self.project,
            "policy": self.policy.name,
            "replaced": len(replaced) + len(post),
            "replaced_by_type": dict(sorted(by_type.items())),
            "replaced_by_detector": dict(sorted(by_detector.items())),
            "kept": [
                {
                    "entity_type": s.entity_type,
                    "text": s.text,
                    "score": s.score,
                    "detector": s.detector,
                }
                for s in kept
            ],
            "distinct_values_in_project": len(self.mapping),
            "detectors_run": sorted(
                {detector_name(d) for d in self.detectors}
                | {"known_values", "known_components"}
            ),
            "post_detectors_run": sorted(detector_name(d) for d in self.post_detectors),
            "caveat": CAVEAT,
        }


#: Entity types promoted out of a kept container span: structured identifiers, whose match is
#: unambiguous. Names are not (a first name inside a kept date: "1. Maj 2024").
PROMOTABLE_TYPES = frozenset(
    {"CPR", "CVR", "EMAIL", "PHONE", "IBAN", "BANK_ACCOUNT", "CASE_ID", "CREDENTIAL"}
)


def _promotable(span: Span) -> bool:
    return span.entity_type in PROMOTABLE_TYPES or tier_of(span.entity_type) == 0


# --------------------------------------------------------------------------- matching helpers

_TOKEN_RE = re.compile(r"\[\s*[A-Z][A-Z_]*\s*[_:\-\s]\s*[\w\-]+\s*\]")
_BRACKETED_RE = re.compile(r"^\[.*\]$|^\[?[A-Z][A-Z_]*[_:\-\s]\s*[\w\-]+\]?$")


def _looks_bracketed(s: str) -> bool:
    return bool(_BRACKETED_RE.match(s.strip()))


def _tolerant_pattern(surrogates: list[str]) -> re.Pattern:
    """One alternation over every surrogate, longest first.

    Bracketed surrogates (``[PERSON_1]``) match loosely: brackets optional, separators loose,
    any case, a genitive allowed after the closing bracket, and a word boundary required when
    the bracket is missing so ``PERSON_1`` never matches inside ``PERSON_11``. Unbracketed
    surrogates (``Alder Brook``, a user alias) match exactly, case included, at word
    boundaries, so ordinary prose that happens to contain the words is left alone.
    """
    alts = []
    for s in sorted(surrogates, key=len, reverse=True):
        if s.startswith("[") and s.endswith("]"):
            parts = [re.escape(p) for p in canon(s).split("_")]
            body = r"[\s_\-]*".join(parts)
            alts.append(rf"\[\s*(?i:{body})\s*\]|(?i:{body})(?![\w])")
        else:
            alts.append(r"\s+".join(re.escape(p) for p in s.split()) + r"(?![\w])")
    return re.compile(r"(?<![\w])(?:" + "|".join(alts) + r")")


def _leftover_tokens(text: str) -> list[str]:
    """Bracketed typed tokens still in *text*: ones the model invented or we never issued."""
    return sorted({m.group(0) for m in _TOKEN_RE.finditer(text)})


def _contains_value(text: str, entity_type: str, original: str) -> bool:
    norm = normalise(entity_type, original)
    if not norm:
        return False
    if entity_type in ("PERSON", "ORG", "ADDRESS"):
        return (
            re.search(rf"(?<![\w]){re.escape(original)}(?![\w])", text) is not None
            or re.search(
                rf"(?<![\w]){re.escape(norm)}(?![\w])", normalise(entity_type, text)
            )
            is not None
        )
    return norm in normalise(entity_type, text) or original in text
