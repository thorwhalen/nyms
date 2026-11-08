"""Deterministic detectors: regular expressions, checksums and gazetteers, no model.

This is the pre-AI pass. Each :class:`Detector` is a compiled pattern plus an optional
validator (a checksum, a calendar check, a stop list) and optional context words that raise
the score when they appear shortly before the match. Any callable ``text -> Iterable[Span]``
is a detector (:class:`DetectorLike`); :class:`Detector` is the regex-backed one this module
ships. A set of them is run by :func:`detect_raw`; :func:`detect` also resolves overlaps.

Design notes, with the research behind them (``docs/research/detection-libraries-and-methods.md``):

- The Danish CPR modulus-11 check is **not a gate**: numbers issued since 1 October 2007 need
  not pass it. A passing check raises the score; a failing one does not drop the match.
- A bare eight-digit number is ambiguous between a Danish phone number and a CVR number. Both
  detectors match it at a low score; the CVR checksum and context words ("CVR", "tlf.")
  decide, and :func:`nyms.spans.resolve_overlaps` keeps the better one.
- Recall over precision: a missed identifier leaks, a redundant replacement only costs
  readability. The capitalised-sequence name heuristic therefore exists, at a low score, and
  the policy threshold decides whether it acts.
- Letters are the Latin letters of Unicode's Basic Latin, Latin-1 Supplement and Latin
  Extended-A and B blocks, upper and lower case as Unicode classifies them, so Danish, Polish,
  Turkish and Spanish names are all names. Text is NFC-normalised by the facade before
  detection, so a decomposed ``ø`` is the same letter as a composed one.
- Credential patterns follow the design of ``openloops.egress`` (vendor prefixes first, one
  heuristic rule last).

>>> spans = detect("Ring til Rasmus Jensen på 12 34 56 78, CPR 010190-1234.")
>>> [(s.entity_type, s.text) for s in spans]
[('PERSON', 'Rasmus Jensen'), ('PHONE', '12 34 56 78'), ('CPR', '010190-1234')]
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from typing import Protocol, runtime_checkable

from nyms.spans import Span, resolve_overlaps
from nyms.taxonomy import SURROGATE_TYPE

Validator = Callable[[re.Match], "float | bool | None"]

CONTEXT_WINDOW = 40  # characters before the match in which a context word counts
CONTEXT_BOOST = 0.3


@runtime_checkable
class DetectorLike(Protocol):
    """Anything that turns text into spans. ``name`` and ``entity_type`` are optional."""

    def __call__(self, text: str) -> Iterable[Span]: ...


def detector_name(detector) -> str:
    """The name a detector reports under: its ``name`` attribute, else its function name."""
    return (
        getattr(detector, "name", None)
        or getattr(detector, "__name__", None)
        or type(detector).__name__
    )


def detector_entity_type(detector) -> str | None:
    """The single entity type a detector emits, when it declares one (regex detectors do)."""
    return getattr(detector, "entity_type", None)


@dataclass(frozen=True)
class Detector:
    """A regex detector with an optional validator and context words.

    ``validate(match)`` may return ``False`` (drop), ``True``/``None`` (keep the base
    score) or a float (use it as the score). ``group`` picks the capture group that is
    the span (the whole match by default). ``value_of(match)`` may name the canonical value
    the span stands for when it differs from the matched text.
    """

    name: str
    entity_type: str
    pattern: re.Pattern
    score: float = 1.0
    validate: Validator | None = None
    group: int | str = 0
    context: tuple[str, ...] = field(default_factory=tuple)
    value_of: Callable[[re.Match], str | None] | None = None

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
            if ctx is not None and ctx.search(
                text[max(0, start - CONTEXT_WINDOW) : start]
            ):
                score = min(1.0, score + CONTEXT_BOOST)
            value = self.value_of(m) if self.value_of is not None else None
            yield Span(
                start,
                end,
                self.entity_type,
                text[start:end],
                round(score, 3),
                self.name,
                value,
            )


@lru_cache(maxsize=None)
def _context_re(words: tuple[str, ...]) -> re.Pattern:
    return re.compile(
        r"(?i)(?<![\w])(?:" + "|".join(re.escape(w) for w in words) + r")"
    )


def normalise_text(text: str) -> str:
    """NFC normalisation and CRLF to LF: the form every detector sees.

    >>> normalise_text('o\\u0308') == '\\u00f6'
    True
    """
    return unicodedata.normalize("NFC", text).replace("\r\n", "\n")


def detect_raw(
    text: str, detectors: Iterable[DetectorLike] | None = None
) -> list[Span]:
    """Run *detectors* (default: :func:`default_detectors`); every span, overlaps included."""
    detectors = default_detectors() if detectors is None else detectors
    found: list[Span] = []
    for d in detectors:
        found.extend(d(text))
    return found


def detect(text: str, detectors: Iterable[DetectorLike] | None = None) -> list[Span]:
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
    # One eight-digit number in eleven passes the checksum by chance: below the default
    # threshold on its own, above it with a context word ("CVR", "SE-nr") or the DK prefix.
    return 0.4 if cvr_ok(m.group(0)) else False


def _dk_phone_validate(m: re.Match):
    text = m.group(0)
    if text.startswith("+") or text.startswith("00"):
        return 1.0
    return 0.7 if re.search(r"[\s.-]", text) else 0.4


def _iban_validate(m: re.Match):
    return 1.0 if iban_ok(m.group(0)) else False


# --------------------------------------------------------------------------- letter classes


def _latin_letters(category: str) -> str:
    """Latin letters of one Unicode category (``Lu`` or ``Ll``) from the blocks up to Extended-B."""
    ranges = (range(0x41, 0x5B), range(0x61, 0x7B), range(0xC0, 0x250))
    return "".join(
        chr(c) for r in ranges for c in r if unicodedata.category(chr(c)) == category
    )


_UC = re.escape(_latin_letters("Lu"))
_LC = re.escape(_latin_letters("Ll"))

#: A capitalised word (``Jensen``, ``Anne-Marie``) or an all-capitals one (``JENSEN``), as in
#: headings; a single capital letter is not a word (so ``N`` in ``København N`` is a suffix).
_CAP_WORD = (
    rf"(?:[{_UC}][{_LC}]+(?:-[{_UC}][{_LC}]+)?|[{_UC}]{{2,}}(?:-[{_UC}]{{2,}})?)"
)
_INITIALS = rf"(?:[{_UC}]\.\s?){{1,3}}"
_PARTICLE = r"(?:von|van|de|der|den|af|la|le|du|di|da)"
# Each step of a name's tail is a capitalised word or an initial, optionally preceded by a
# particle ("von", "af"); a particle never ends a name ("Mette Holm af 2. september").
_NAME_TAIL = rf"(?:\s(?:{_PARTICLE}\s)?(?:{_CAP_WORD}|[{_UC}]\.)){{0,3}}"

# --------------------------------------------------------------------------- patterns

_DK_STREET_SUFFIX = (
    r"(?:vej|vejen|gade|gaden|allé|alle|plads|boulevard|stræde|vænge|vænget|vang|vangen|parken|park|haven|have|"
    r"torv|torvet|bakke|bakken|høj|højen|holm|holmen|stien|sti|marken|mark|dalen|dal|lund|lunden|gården|gård|"
    r"kær|kæret|skoven|skov|ager|ageren|toften|toft|engen|eng|bro|broen|strand|stranden|kvarter|kvarteret|"
    r"centret|center|krogen|krog|hegnet|hegn|gyde|gyden|led|leddet|husene|huse)"
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
    has_suffix = (
        re.search(_DK_STREET_SUFFIX + r"$", street.split()[-1], re.IGNORECASE)
        is not None
    )
    if m.group("post"):
        return 0.95
    return 0.8 if has_suffix else False


_CUR = r"(?:DKK|kr\.?|EUR|€|USD|\$|£|GBP|SEK|NOK|CHF)"
# As a suffix, "kr." keeps its period only when the sentence goes on in lower case; before an
# upper-case word or the end of the text the period is the sentence's, not the unit's.
_CUR_SUFFIX = rf"(?:DKK|kr\.(?!\s*(?:[{_UC}]|$))|kr|EUR|€|USD|\$|£|GBP|SEK|NOK|CHF)"
_NUM = r"(?:\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
_SCALE = r"(?:\s?(?:mio|mia|mill|millioner|million|billion|tusind|thousand|k)\.?(?=[\s,;)]|$))?"
_AMOUNT = re.compile(
    rf"(?<![\w.,]){_CUR}\s?{_NUM}{_SCALE}(?![\d])|(?<![\w.,]){_NUM}{_SCALE}\s?(?:{_CUR_SUFFIX}|,-)(?![{_LC}])"
)

_MONTHS_DA = r"(?:januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|okt|nov|dec)\.?"
_MONTHS_EN = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?"
)
_DATE = re.compile(
    r"(?<!\d)(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-](?:\d{4}|\d{2}))(?!\d)"
    rf"|(?<![\w])(?:den\s)?\d{{1,2}}\.?\s{_MONTHS_DA}(?:\s\d{{4}})?(?![{_LC}])"
    rf"|(?<![\w])\d{{1,2}}(?:st|nd|rd|th)?\s(?:of\s)?{_MONTHS_EN}(?:,?\s\d{{4}})?\b"
    rf"|(?<![\w]){_MONTHS_EN}\s\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s\d{{4}})?\b"
)

_CASE_ID_CODE = re.compile(r"\b(?:BS|SS|B|S|K|V)-\d{1,6}/\d{4}(?:-[A-Z]{3})?\b")
_CASE_ID_LABELLED = re.compile(
    r"(?i:(?:sagsnr|sags\s?nr|j\.?\s?nr|journalnr|sag\s?nr|case\s(?:no|number)|ref\.?\s?nr)\.?\s*:?\s*)(?P<id>[A-Z0-9][\w\-/]{3,}(?<![.,;]))"
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
    (
        "json_web_token",
        r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+",
    ),
    (
        "private_key_block",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
    ),
    (
        "secret_assignment",
        r"(?i)(?<![A-Za-z0-9])(?:[A-Za-z0-9]+[_-])*(?:api[_-]?key|secret[_-]?\w*|passwd|password|access[_-]?token|auth[_-]?token|token|credential\w*)\b\s*[:=]\s*['\"]?((?=[^'\"\s]*[A-Za-z])(?=[^'\"\s]*\d)[A-Za-z0-9+/=_\-.]{16,})['\"]?",
    ),
]

_TITLES = (
    r"(?:\b(?:Hr|Fru|Frk|Mr|Mrs|Ms|Mx|Dr|Prof|Adv|Sir)\.?|\b(?:advokat|Advokat|direktør|Direktør|sagsøger|Sagsøger|"
    r"sagsøgte|Sagsøgte|klager|Klager|indklagede|Indklagede|lejer|Lejer|udlejer|Udlejer|vidne|Vidne|dommer|Dommer))"
)
_TITLE_NAME = re.compile(
    rf"{_TITLES}\s+(?P<name>(?:{_INITIALS})?{_CAP_WORD}{_NAME_TAIL})"
)

_HEURISTIC_NAME = re.compile(
    rf"(?<![{_UC}{_LC}\-])(?P<name>(?:{_INITIALS}|{_CAP_WORD})(?:\s(?:{_PARTICLE}\s)?{_CAP_WORD}){{1,3}})(?![{_UC}{_LC}])"
)

_ORG_SUFFIX = r"(?:ApS|A/S|I/S|IVS|K/S|P/S|Ltd\.?|Limited|Inc\.?|LLC|LLP|PLC|GmbH|AG|SA|S\.A\.|BV|B\.V\.|AB|AS|ASA|Oy|Oyj|Corp\.?|Co\.|Holding|Fonden|Foundation)"
_ORG_NAME = re.compile(
    rf"(?<![{_UC}{_LC}\-])(?P<name>{_CAP_WORD}(?:\s(?:(?:&|og|and|{_PARTICLE})\s)?{_CAP_WORD}){{0,4}}\s{_ORG_SUFFIX})(?![{_UC}{_LC}])"
)

#: Capitalised words that start or end a sequence which is not a person's name.
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
        "Januar Februar Marts Maj Juni Juli Oktober Jan Feb Mar Apr Jun Jul Aug Sep Sept Okt Oct Nov Dec "
        "CPR CVR IBAN BIC SWIFT DKK EUR USD GBP SEK NOK NR Nr ApS IVS LLC Ltd PLC GmbH Google Microsoft Apple Claude Anthropic OpenAI ChatGPT"
    ).split()
)


def _heuristic_name_validate(m: re.Match):
    words = m.group("name").split()
    if (
        words[0].casefold().rstrip(".") in NAME_STOPWORDS
        or words[-1].casefold() in NAME_STOPWORDS
    ):
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
        text = (
            resources.files("nyms.data.names")
            .joinpath(f"first_names_{lang}.txt")
            .read_text("utf-8")
        )
        names.update(w.casefold() for w in text.split())
    return frozenset(names)


def gazetteer_detector(
    names: Iterable[str],
    *,
    name: str = "gazetteer",
    entity_type: str = "PERSON",
    score: float = 1.0,
    surname_tail: bool = True,
    value_of_name: Callable[[str], str | None] | None = None,
    single_word_score: float = 0.85,
) -> Detector:
    """A detector for a list of known names (full names or first names), case-insensitive.

    A first name followed by capitalised words extends to the full name when *surname_tail*
    is true. A genitive ``s`` on the last word stays in the span; the mapping store decides
    whether it is a genitive of a known value. *value_of_name* may map the matched text to the
    canonical value it stands for (a surname to the full name).

    >>> d = gazetteer_detector(['Rasmus'])
    >>> [s.text for s in d('Rasmus Jensens bil, og Rasmus selv.')]
    ['Rasmus Jensens', 'Rasmus']
    """
    alts = sorted({n.strip() for n in names if n.strip()}, key=len, reverse=True)
    if not alts:
        return Detector(name, entity_type, re.compile(r"(?!x)x"), score)
    alt = "|".join(re.escape(n) for n in alts)
    tail = _NAME_TAIL if surname_tail else ""
    # The list is matched case-insensitively (headings are upper case) but the head must start
    # with a capital: "jan" in "1. jan. 2024" is a month, "Jan" is a name. A genitive "s" after
    # the name is matched but left outside the span.
    pattern = re.compile(
        rf"(?<![{_UC}{_LC}])(?P<name>(?i:{alt})(?:-{_CAP_WORD})?{tail})(?:(?:'s|’s|s)(?![{_UC}{_LC}])|(?![{_UC}{_LC}]))"
    )

    def validate(m: re.Match):
        name = m.group("name")
        if not name[0].isupper():
            return False
        return score if " " in name else min(score, single_word_score)

    value_of = (lambda m: value_of_name(m.group("name"))) if value_of_name else None
    return Detector(
        name, entity_type, pattern, score, validate, "name", value_of=value_of
    )


def default_detectors(
    *, names: Iterable[str] = (), languages: tuple[str, ...] = ("da", "en")
) -> list[Detector]:
    """The deterministic detector set. *names* are the parties you already know.

    Order does not matter for the result (overlaps are resolved afterwards), only for the
    report's grouping.
    """
    detectors = [
        Detector(
            "cpr",
            "CPR",
            re.compile(r"(?<![\d])\d{6}-?\d{4}(?![\d])"),
            0.9,
            _cpr_validate,
            context=(
                "cpr",
                "cpr-nr",
                "cpr-nummer",
                "personnummer",
                "person nr",
                "fødselsnummer",
            ),
        ),
        Detector(
            "cvr",
            "CVR",
            re.compile(r"(?<![\w])\d{8}(?![\d])"),
            0.4,
            _cvr_validate,
            context=(
                "cvr",
                "cvr-nr",
                "cvr-nummer",
                "se-nr",
                "se-nummer",
                "vat",
                "moms",
            ),
        ),
        Detector("dk_vat", "CVR", re.compile(r"\bDK\s?\d{8}\b"), 0.95),
        Detector("email", "EMAIL", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), 1.0),
        Detector(
            "dk_phone",
            "PHONE",
            re.compile(
                r"(?<![\d+])(?:\+45[\s.-]?|0045[\s.-]?)?(?:\d{2}[\s.-]?){3}\d{2}(?![\d])"
            ),
            0.7,
            _dk_phone_validate,
            context=("tlf", "telefon", "mobil", "mob", "phone", "tel", "ring"),
        ),
        Detector(
            "intl_phone",
            "PHONE",
            re.compile(
                r"(?<![\d])\+(?!45)\d{1,3}[\s.-]?\(?\d{1,4}\)?(?:[\s.-]?\d{2,4}){2,4}(?![\d])"
            ),
            0.9,
        ),
        Detector(
            "iban",
            "IBAN",
            re.compile(
                r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,4})?\b"
            ),
            1.0,
            _iban_validate,
        ),
        Detector(
            "dk_bank_account",
            "BANK_ACCOUNT",
            re.compile(
                r"(?<![\d])\d{4}(?:[\s-]|\s?(?i:konto(?:nr|nummer)?\.?)\s?)\d{6,10}(?![\d])"
            ),
            0.6,
            context=(
                "konto",
                "kontonr",
                "kontonummer",
                "reg",
                "reg.nr",
                "registreringsnummer",
                "account",
                "bank",
            ),
        ),
        Detector("dk_address", "ADDRESS", _DK_ADDRESS, 0.9, _dk_address_validate),
        Detector("en_address", "ADDRESS", _EN_ADDRESS, 0.9),
        Detector(
            "dk_postcode_city",
            "POSTCODE_CITY",
            re.compile(rf"(?<![\d]){_DK_POSTCODE_CITY}(?![{_LC}])"),
            0.6,
        ),
        Detector("amount", "AMOUNT", _AMOUNT, 0.95),
        Detector("date", "DATE", _DATE, 0.9),
        Detector("case_id", "CASE_ID", _CASE_ID_CODE, 0.9),
        Detector("case_id_labelled", "CASE_ID", _CASE_ID_LABELLED, 0.9, None, "id"),
        Detector(
            "url",
            "URL",
            re.compile(r"\bhttps?://[^\s<>\"')\]]+|\bwww\.[^\s<>\"')\]]+"),
            1.0,
        ),
        Detector("org_name", "ORG", _ORG_NAME, 0.9, None, "name"),
        Detector("title_name", "PERSON", _TITLE_NAME, 0.9, None, "name"),
        Detector(
            "heuristic_name",
            "PERSON",
            _HEURISTIC_NAME,
            0.5,
            _heuristic_name_validate,
            "name",
        ),
    ]
    detectors.extend(
        Detector(
            f"credential:{n}",
            "CREDENTIAL",
            re.compile(p),
            1.0,
            None,
            1 if n == "secret_assignment" else 0,
        )
        for n, p in _CREDENTIAL_PATTERNS
    )
    if languages:
        detectors.append(
            gazetteer_detector(
                bundled_first_names(*languages), name="first_names", score=0.9
            )
        )
    names = [n for n in names if n and n.strip()]
    if names:
        detectors.append(gazetteer_detector(names, name="known_names", score=1.0))
    return detectors


def name_components(full_names: Iterable[str]) -> dict[str, str]:
    """``{component: full name}`` for the tokens that identify exactly one of *full_names*.

    A surname or first name alone stands for the person when no other known name shares it;
    stop words, short tokens and particles never do.

    >>> name_components(['Rasmus Jensen', 'Mette Jensen'])
    {'rasmus': 'Rasmus Jensen', 'mette': 'Mette Jensen'}
    """
    owners: dict[str, set[str]] = {}
    for full in full_names:
        words = full.split()
        if len(words) < 2:
            continue
        for w in words:
            key = w.casefold().strip(".,")
            if len(key) < 3 or key in NAME_STOPWORDS or re.fullmatch(_PARTICLE, key):
                continue
            owners.setdefault(key, set()).add(full)
    return {k: next(iter(v)) for k, v in owners.items() if len(v) == 1}


def known_values_detectors(
    records: Iterable, *, extra_names: Iterable[str] = (), score: float = 1.0
) -> list[Detector]:
    """Detectors for what a project already knows: its values, their name components, its surrogates.

    - every original in the mapping, by type: names through :func:`gazetteer_detector` (word
      boundaries, genitive), everything else literally;
    - for persons, each component (first name or surname) that identifies exactly one known
      person, standing for the full name (``Span.value``), scored above a lone first name from
      the bundled list so the known person wins;
    - every surrogate already issued, as :data:`SURROGATE_TYPE`, so the project's own
      surrogates are never re-detected as names when pseudonymised text is processed again.
    """
    recs = list(getattr(records, "records", lambda: records)())
    by_type: dict[str, set[str]] = {}
    for rec in recs:
        by_type.setdefault(rec.entity_type, set()).add(rec.original)
    out: list[Detector] = []
    for entity_type, values in sorted(by_type.items()):
        if entity_type in ("PERSON", "ORG"):
            out.append(
                gazetteer_detector(
                    values,
                    name="known_values",
                    entity_type=entity_type,
                    score=score,
                    surname_tail=False,
                )
            )
        else:
            alt = "|".join(re.escape(v) for v in sorted(values, key=len, reverse=True))
            out.append(
                Detector(
                    "known_values",
                    entity_type,
                    re.compile(rf"(?<![\w])(?:{alt})(?![\w])"),
                    score,
                )
            )
    persons = by_type.get("PERSON", set()) | {n for n in extra_names if n and n.strip()}
    components = name_components(persons)
    if components:
        out.append(
            gazetteer_detector(
                components,
                name="known_components",
                entity_type="PERSON",
                score=0.95,
                surname_tail=False,
                single_word_score=0.95,
                value_of_name=lambda text: components.get(
                    re.sub(r"(?:'s|’s|s)$", "", text.casefold()),
                    components.get(text.casefold()),
                ),
            )
        )
    surrogates = sorted({r.surrogate for r in recs}, key=len, reverse=True)
    if surrogates:
        alt = "|".join(re.escape(s) for s in surrogates)
        out.append(
            Detector(
                "surrogates",
                SURROGATE_TYPE,
                re.compile(rf"(?<![\w])(?:{alt})(?![\w])"),
                1.0,
            )
        )
    return out
