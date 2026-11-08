"""Deterministic detectors: regular expressions, checksums and gazetteers, no model.

This is the pre-AI pass. Each :class:`Detector` is a compiled pattern plus an optional
validator (a checksum, a calendar check, a stop list) and optional context words that raise
the score when they appear shortly before the match. A detector is a callable
``text -> Iterator[Span]``; a set of them is run by :func:`detect`, which resolves overlaps.

Design notes, with the research behind them (``docs/research/detection-libraries-and-methods.md``):

- The Danish CPR modulus-11 check is **not a gate**: numbers issued since 1 October 2007 need
  not pass it. A passing check raises the score; a failing one does not drop the match.
- A bare eight-digit number is ambiguous between a Danish phone number and a CVR number. Both
  detectors match it at a low score; the CVR checksum and context words ("CVR", "tlf.")
  decide, and :func:`nyms.spans.resolve_overlaps` keeps the better one.
- Recall over precision: a missed identifier leaks, a redundant replacement only costs
  readability. The capitalised-sequence name heuristic therefore exists, at a low score, and
  the policy threshold decides whether it acts.
- Credential patterns follow the design of ``openloops.egress`` (vendor prefixes first, one
  heuristic rule last).

>>> spans = detect("Ring til Rasmus Jensen på 12 34 56 78, CPR 010190-1234.")
>>> [(s.entity_type, s.text) for s in spans]
[('PERSON', 'Rasmus Jensen'), ('PHONE', '12 34 56 78'), ('CPR', '010190-1234')]
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

from nyms.spans import Span, resolve_overlaps

Validator = Callable[[re.Match], "float | bool | None"]

CONTEXT_WINDOW = 40  # characters before the match in which a context word counts
CONTEXT_BOOST = 0.3


@dataclass(frozen=True)
class Detector:
    """A regex detector with an optional validator and context words.

    ``validate(match)`` may return ``False`` (drop), ``True``/``None`` (keep the base
    score) or a float (use it as the score). ``group`` picks the capture group that is
    the span (the whole match by default).
    """

    name: str
    entity_type: str
    pattern: re.Pattern
    score: float = 1.0
    validate: Validator | None = None
    group: int | str = 0
    context: tuple[str, ...] = field(default_factory=tuple)

    def __call__(self, text: str) -> Iterator[Span]:
        ctx = _context_re(self.context) if self.context else None
        for m in self.pattern.finditer(text):
            score = self.score
            if self.validate is not None:
                v = self.validate(m)
                if v is False:
                    continue
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    score = float(v)
            start, end = m.span(self.group)
            if start == end:
                continue
            if ctx is not None and ctx.search(text[max(0, start - CONTEXT_WINDOW) : start]):
                score = min(1.0, score + CONTEXT_BOOST)
            yield Span(start, end, self.entity_type, text[start:end], round(score, 3), self.name)


@lru_cache(maxsize=None)
def _context_re(words: tuple[str, ...]) -> re.Pattern:
    return re.compile(r"(?i)(?<![\w])(?:" + "|".join(re.escape(w) for w in words) + r")")


def detect_raw(text: str, detectors: Iterable[Detector] | None = None) -> list[Span]:
    """Run *detectors* (default: :func:`default_detectors`); every span, overlaps included."""
    detectors = default_detectors() if detectors is None else detectors
    found: list[Span] = []
    for d in detectors:
        found.extend(d(text))
    return found


def detect(text: str, detectors: Iterable[Detector] | None = None) -> list[Span]:
    """Run *detectors* (default: :func:`default_detectors`) and resolve overlaps."""
    return resolve_overlaps(detect_raw(text, detectors))


# --------------------------------------------------------------------------- validators


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def cpr_mod11_ok(cpr: str) -> bool:
    """The historical CPR modulus-11 check. Not required for numbers issued after 2007.

    >>> cpr_mod11_ok('211062-5629')
    True
    >>> cpr_mod11_ok('010190-1234')
    False
    """
    d = _digits(cpr)
    if len(d) != 10:
        return False
    weights = (4, 3, 2, 7, 6, 5, 4, 3, 2, 1)
    return sum(int(c) * w for c, w in zip(d, weights)) % 11 == 0


def cpr_date_ok(cpr: str) -> bool:
    """Whether the first six digits are a plausible DDMMYY date.

    >>> cpr_date_ok('311299-0001'), cpr_date_ok('321299-0001'), cpr_date_ok('011399-0001')
    (True, False, False)
    """
    d = _digits(cpr)
    if len(d) < 6:
        return False
    day, month = int(d[:2]), int(d[2:4])
    return 1 <= day <= 31 and 1 <= month <= 12


def cvr_ok(cvr: str) -> bool:
    """The CVR modulus-11 check (weights 2 7 6 5 4 3 2 1).

    >>> cvr_ok('10150817'), cvr_ok('12345678')
    (True, False)
    """
    d = _digits(cvr)
    if len(d) != 8 or d[0] == "0":
        return False
    weights = (2, 7, 6, 5, 4, 3, 2, 1)
    return sum(int(c) * w for c, w in zip(d, weights)) % 11 == 0


def iban_ok(iban: str) -> bool:
    """ISO 13616 mod-97 check.

    >>> iban_ok('DK50 0040 0440 1162 43'), iban_ok('DK50 0040 0440 1162 44')
    (True, False)
    """
    s = re.sub(r"\s", "", iban).upper()
    if not (15 <= len(s) <= 34) or not s[:2].isalpha() or not s[2:4].isdigit():
        return False
    rearranged = s[4:] + s[:4]
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    return int(numeric) % 97 == 1


def _cpr_validate(m: re.Match):
    text = m.group(0)
    if not cpr_date_ok(text):
        return False
    score = 0.9 if "-" in text else 0.7
    return min(1.0, score + (0.1 if cpr_mod11_ok(text) else 0.0))


def _cvr_validate(m: re.Match):
    return 0.5 if cvr_ok(m.group(0)) else False


def _dk_phone_validate(m: re.Match):
    text = m.group(0)
    if text.startswith("+") or text.startswith("00"):
        return 1.0
    return 0.7 if re.search(r"[\s.-]", text) else 0.4


def _iban_validate(m: re.Match):
    return 1.0 if iban_ok(m.group(0)) else False


# --------------------------------------------------------------------------- patterns

_UC = "A-ZÆØÅÉÜÖÄ"
_LC = "a-zæøåéüöäß"
_CAP_WORD = rf"[{_UC}][{_LC}]+(?:-[{_UC}][{_LC}]+)?"
_PARTICLE = r"(?:von|van|de|der|den|af|la|le|du|di|da)"
# Each step of a name's tail is a capitalised word or an initial, optionally preceded by a
# particle ("von", "af"); a particle never ends a name ("Mette Holm af 2. september").
_NAME_TAIL = rf"(?:\s(?:{_PARTICLE}\s)?(?:{_CAP_WORD}|[{_UC}]\.)){{0,3}}"
_GENITIVE = r"(?:'s|’s|s)?"

_DK_STREET_SUFFIX = (
    r"(?:vej|vejen|gade|gaden|allé|alle|plads|boulevard|stræde|vænge|vænget|vang|vangen|parken|park|haven|have|"
    r"torv|torvet|bakke|bakken|høj|højen|holm|holmen|stien|sti|marken|mark|dalen|dal|lund|lunden|gården|gård|"
    r"kær|kæret|skoven|skov|ager|ageren|toften|toft|engen|eng|bro|broen|strand|stranden|kvarter|kvarteret|"
    r"centret|center|krogen|krog|hegnet|hegn|gyde|gyden|led|leddet|husene|huse|bakkevej|søvej|strandvej)"
)
_DK_STREET = rf"{_CAP_WORD}(?:\s{_CAP_WORD}){{0,3}}"
# A floor is "st.", "kl." or "3." (the period is mandatory, or ", 16" of a postcode would be a floor).
_DK_FLOOR = r"(?:,?\s(?:st|kl|\d{1,2})\.(?:\s?(?:th|tv|mf|sal)\.?)?)?"
# Danish towns may end in a compass letter: "København N", "København SV".
_DK_POSTCODE_CITY = rf"\d{{4}}\s{_CAP_WORD}(?:\s{_CAP_WORD}){{0,2}}(?:\s[NSØVK]{{1,2}}(?![{_UC}{_LC}]))?"
_DK_ADDRESS = re.compile(
    rf"(?<![{_UC}{_LC}])(?P<street>{_DK_STREET})\s(?P<number>\d{{1,4}}[A-Za-z]?){_DK_FLOOR}"
    rf"(?P<post>,?\s{_DK_POSTCODE_CITY})?(?![{_LC}])"
)
_EN_STREET_SUFFIX = (
    r"(?:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?|Lane|Ln\.?|Drive|Dr\.?|Boulevard|Blvd\.?|Court|Ct\.?|"
    r"Place|Pl\.?|Way|Square|Sq\.?|Terrace|Close|Crescent|Gardens|Row)"
)
_EN_ADDRESS = re.compile(
    rf"\b\d{{1,5}}[A-Za-z]?\s(?:[A-Z][a-z]+\s){{1,3}}{_EN_STREET_SUFFIX}\b"
    r"(?:,\s[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)?(?:,?\s(?:[A-Z]{2}\s\d{5}|[A-Z]{1,2}\d{1,2}[A-Z]?\s\d[A-Z]{2}))?"
)


def _dk_address_validate(m: re.Match):
    street = m.group("street")
    has_suffix = re.search(_DK_STREET_SUFFIX + r"$", street.split()[-1], re.IGNORECASE) is not None
    if m.group("post"):
        return 0.95
    return 0.8 if has_suffix else False


_CUR = r"(?:DKK|kr\.?|EUR|€|USD|\$|£|GBP|SEK|NOK|CHF)"
# As a suffix, "kr." keeps its period only when the sentence goes on in lower case; before an
# upper-case word or the end of the text the period is the sentence's, not the unit's.
_CUR_SUFFIX = rf"(?:DKK|kr\.(?!\s*(?:[{_UC}]|$))|kr|EUR|€|USD|\$|£|GBP|SEK|NOK|CHF)"
_NUM = r"(?:\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
_SCALE = r"(?:\s?(?:mio\.?|mia\.?|mill\.?|millioner|million|billion|tusind|thousand|k)\b)?"
_AMOUNT = re.compile(
    rf"(?<![\w.,]){_CUR}\s?{_NUM}{_SCALE}(?![\d])|(?<![\w.,]){_NUM}{_SCALE}\s?(?:{_CUR_SUFFIX}|,-)(?![{_LC}])"
)

_MONTHS_DA = r"(?:januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december)"
_MONTHS_EN = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
)
_DATE = re.compile(
    r"(?<!\d)(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-](?:\d{4}|\d{2}))(?!\d)"
    rf"|(?<![\w])(?:den\s)?\d{{1,2}}\.?\s{_MONTHS_DA}(?:\s\d{{4}})?\b"
    rf"|(?<![\w])\d{{1,2}}(?:st|nd|rd|th)?\s(?:of\s)?{_MONTHS_EN}(?:,?\s\d{{4}})?\b"
    rf"|(?<![\w]){_MONTHS_EN}\s\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s\d{{4}})?\b"
)

_CASE_ID = re.compile(
    r"\b(?:BS|SS|B|S|K|V)-\d{1,6}/\d{4}(?:-[A-Z]{3})?\b"
    r"|(?i:(?:sagsnr|sags\s?nr|j\.?\s?nr|journalnr|sag\s?nr|case\s(?:no|number)|ref\.?\s?nr)\.?\s*:?\s*)(?P<id>[A-Z0-9][\w\-/.]{3,})"
)



_CREDENTIAL_PATTERNS = [
    ("aws_access_key_id", r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])"),
    ("github_token", r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    ("github_pat", r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    ("anthropic_api_key", r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"),
    ("openai_api_key", r"\bsk-(?!ant-)[A-Za-z0-9_\-]{20,}\b"),
    ("stripe_key", r"\b[srp]k_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    ("slack_token", r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
    ("google_api_key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    ("json_web_token", r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+"),
    ("private_key_block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    (
        "secret_assignment",
        r"(?i)(?<![A-Za-z0-9])(?:[A-Za-z0-9]+[_-])*(?:api[_-]?key|secret[_-]?\w*|passwd|password|access[_-]?token|auth[_-]?token|token|credential\w*)\b\s*[:=]\s*['\"]?((?=[^'\"\s]*[A-Za-z])(?=[^'\"\s]*\d)[A-Za-z0-9+/=_\-.]{16,})['\"]?",
    ),
]

_TITLES = (
    r"(?:\b(?:Hr|Fru|Frk|Mr|Mrs|Ms|Mx|Dr|Prof|Adv|Sir)\.?|\b(?:advokat|Advokat|direktør|Direktør|sagsøger|Sagsøger|"
    r"sagsøgte|Sagsøgte|klager|Klager|indklagede|Indklagede|lejer|Lejer|udlejer|Udlejer|vidne|Vidne|dommer|Dommer))"
)
_TITLE_NAME = re.compile(rf"{_TITLES}\s+(?P<name>{_CAP_WORD}{_NAME_TAIL})")

_HEURISTIC_NAME = re.compile(rf"(?<![{_UC}{_LC}\-])(?P<name>{_CAP_WORD}(?:\s(?:{_PARTICLE}\s)?{_CAP_WORD}){{1,3}})(?![{_UC}{_LC}])")

_ORG_SUFFIX = r"(?:ApS|A/S|I/S|IVS|K/S|P/S|Ltd\.?|Limited|Inc\.?|LLC|LLP|PLC|GmbH|AG|SA|S\.A\.|BV|B\.V\.|AB|AS|ASA|Oy|Oyj|Corp\.?|Co\.|Holding|Fonden|Foundation)"
_ORG_NAME = re.compile(rf"(?<![{_UC}{_LC}\-])(?P<name>{_CAP_WORD}(?:\s(?:(?:&|og|and|{_PARTICLE})\s)?{_CAP_WORD}){{0,4}}\s{_ORG_SUFFIX})(?![{_UC}{_LC}])")

#: Capitalised words that start a sequence which is not a person's name.
NAME_STOPWORDS = frozenset(
    w.casefold()
    for w in (
        "Den Det De Der Her Hvis Når Som Men Og Eller For Med Til Fra Ved Om På Af I Jeg Du Vi Han Hun Dette Denne Disse "
        "Kære Hilsen Venlig Mvh Bilag Punkt Side Dato Emne Vedr Vedrørende Att Retten Byretten Landsretten Højesteret "
        "Østre Vestre Sø Danmark Dansk Danske Danmarks København Københavns Aarhus Odense Aalborg Europa Europæiske Ministeriet "
        "Styrelsen Kommune Kommunen Region Regionen Staten Folketinget Regeringen Domstolen Domstolene Nævnet Ankestyrelsen "
        "The This That These Those In On At By For From With To Of And Or But If When Dear Regards Sincerely Best Kind Yours "
        "Subject Re Date Page Attachment Section Article Court High Supreme District Appeal Appeals European Union United Kingdom "
        "States America Denmark Danish English Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March "
        "April June July August September October November December Mandag Tirsdag Onsdag Torsdag Fredag Lørdag Søndag "
        "Januar Februar Marts Maj Juni Juli Oktober Google Microsoft Apple Claude Anthropic OpenAI ChatGPT"
    ).split()
)


def _heuristic_name_validate(m: re.Match):
    words = m.group("name").split()
    if words[0].casefold() in NAME_STOPWORDS or words[-1].casefold() in NAME_STOPWORDS:
        return False
    if all(w.casefold() in NAME_STOPWORDS for w in words):
        return False
    before = m.string[: m.start()].rstrip()
    sentence_start = not before or before[-1] in ".!?:\n"
    return 0.4 if sentence_start else 0.5


@lru_cache(maxsize=None)
def bundled_first_names(*languages: str) -> frozenset[str]:
    """The bundled first-name gazetteers (``da``, ``en``), casefolded.

    >>> 'rasmus' in bundled_first_names('da')
    True
    """
    languages = languages or ("da", "en")
    names: set[str] = set()
    for lang in languages:
        text = resources.files("nyms.data.names").joinpath(f"first_names_{lang}.txt").read_text("utf-8")
        names.update(w.casefold() for w in text.split())
    return frozenset(names)


def gazetteer_detector(
    names: Iterable[str], *, name: str = "gazetteer", entity_type: str = "PERSON", score: float = 1.0, surname_tail: bool = True
) -> Detector:
    """A detector for a list of known names (full names or first names).

    A first name followed by capitalised words extends to the full name when *surname_tail*
    is true. The Danish genitive ``-s`` is left outside the span so the same person maps to
    the same surrogate; the core re-attaches it.

    >>> d = gazetteer_detector(['Rasmus'])
    >>> [s.text for s in d('Rasmus Jensens bil, og Rasmus selv.')]
    ['Rasmus Jensen', 'Rasmus']
    """
    alts = sorted({n.strip() for n in names if n.strip()}, key=len, reverse=True)
    if not alts:
        return Detector(name, entity_type, re.compile(r"(?!x)x"), score)
    alt = "|".join(re.escape(n) for n in alts)
    tail = _NAME_TAIL if surname_tail else ""
    pattern = re.compile(rf"(?<![{_UC}{_LC}])(?P<name>(?i:{alt}){tail})(?=s\b|'s|’s|[^{_UC}{_LC}]|$)")

    def validate(m: re.Match):
        return score if " " in m.group("name") else min(score, 0.85)

    return _Gazetteer(name, entity_type, pattern, score, validate, "name")


class _Gazetteer(Detector):
    """A gazetteer detector that strips a genitive ``s`` from a matched surname."""

    def __call__(self, text: str) -> Iterator[Span]:
        for s in super().__call__(text):
            yield _strip_surname_genitive(s)


def _strip_surname_genitive(span: Span) -> Span:
    """``Rasmus Jensens`` -> ``Rasmus Jensen`` when the last word has a trailing ``s``."""
    words = span.text.split()
    if len(words) > 1 and words[-1].endswith("s") and len(words[-1]) > 3 and not words[-1].endswith("ss"):
        new_text = span.text[:-1]
        return Span(span.start, span.end - 1, span.entity_type, new_text, span.score, span.detector)
    return span


def default_detectors(*, names: Iterable[str] = (), languages: tuple[str, ...] = ("da", "en")) -> list[Detector]:
    """The deterministic detector set. *names* are the parties you already know.

    Order does not matter for the result (overlaps are resolved afterwards), only for the
    report's grouping.
    """
    detectors = [
        Detector("cpr", "CPR", re.compile(r"(?<![\d])\d{6}-?\d{4}(?![\d])"), 0.9, _cpr_validate,
                 context=("cpr", "cpr-nr", "cpr-nummer", "personnummer", "person nr", "fødselsnummer")),
        Detector("cvr", "CVR", re.compile(r"(?<![\w])\d{8}(?![\d])"), 0.5, _cvr_validate,
                 context=("cvr", "cvr-nr", "cvr-nummer", "se-nr", "se-nummer", "vat", "moms")),
        Detector("dk_vat", "CVR", re.compile(r"\bDK\s?\d{8}\b"), 0.95),
        Detector("email", "EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), 1.0),
        Detector("dk_phone", "PHONE", re.compile(r"(?<![\d+])(?:\+45[\s.-]?|0045[\s.-]?)?(?:\d{2}[\s.-]?){3}\d{2}(?![\d])"), 0.7,
                 _dk_phone_validate, context=("tlf", "telefon", "mobil", "mob", "phone", "tel", "ring")),
        Detector("intl_phone", "PHONE", re.compile(r"(?<![\d])\+(?!45)\d{1,3}[\s.-]?\(?\d{1,4}\)?(?:[\s.-]?\d{2,4}){2,4}(?![\d])"), 0.9),
        Detector("iban", "IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b"), 1.0, _iban_validate),
        Detector("dk_bank_account", "BANK_ACCOUNT", re.compile(r"(?<![\d])\d{4}(?:[\s-]|\s?(?i:konto(?:nr|nummer)?\.?)\s?)\d{6,10}(?![\d])"), 0.6,
                 context=("konto", "kontonr", "kontonummer", "reg", "reg.nr", "registreringsnummer", "account", "bank")),
        Detector("dk_address", "ADDRESS", _DK_ADDRESS, 0.9, _dk_address_validate),
        Detector("en_address", "ADDRESS", _EN_ADDRESS, 0.9),
        Detector("dk_postcode_city", "POSTCODE_CITY", re.compile(rf"(?<![\d]){_DK_POSTCODE_CITY}(?![{_LC}])"), 0.6),
        Detector("amount", "AMOUNT", _AMOUNT, 0.95),
        Detector("date", "DATE", _DATE, 0.9),
        Detector("case_id", "CASE_ID", _CASE_ID, 0.9),
        Detector("url", "URL", re.compile(r"\bhttps?://[^\s<>\"')\]]+|\bwww\.[^\s<>\"')\]]+"), 1.0),
        Detector("org_name", "ORG", _ORG_NAME, 0.9, None, "name"),
        Detector("title_name", "PERSON", _TITLE_NAME, 0.9, None, "name"),
        Detector("heuristic_name", "PERSON", _HEURISTIC_NAME, 0.5, _heuristic_name_validate, "name"),
    ]
    detectors.extend(
        Detector(f"credential:{n}", "CREDENTIAL", re.compile(p), 1.0, None, 1 if n == "secret_assignment" else 0)
        for n, p in _CREDENTIAL_PATTERNS
    )
    if languages:
        detectors.append(gazetteer_detector(bundled_first_names(*languages), name="first_names", score=0.9))
    names = [n for n in names if n and n.strip()]
    if names:
        detectors.append(gazetteer_detector(names, name="known_names", score=1.0))
    return detectors


def known_values_detectors(records: Iterable, *, score: float = 1.0) -> list[Detector]:
    """One detector per entity type for the originals already in a mapping store.

    Names and organisations go through :func:`gazetteer_detector` (word boundaries, genitive
    handling); everything else is matched literally. This is what makes every occurrence of a
    known value consistent, within a document and across the project.
    """
    by_type: dict[str, set[str]] = {}
    for rec in getattr(records, "records", lambda: records)():
        by_type.setdefault(rec.entity_type, set()).add(rec.original)
    out = []
    for entity_type, values in sorted(by_type.items()):
        if entity_type in ("PERSON", "ORG"):
            out.append(gazetteer_detector(values, name="known_values", entity_type=entity_type, score=score, surname_tail=False))
        else:
            alt = "|".join(re.escape(v) for v in sorted(values, key=len, reverse=True))
            out.append(Detector("known_values", entity_type, re.compile(rf"(?<![\w])(?:{alt})(?![\w])"), score))
    return out
