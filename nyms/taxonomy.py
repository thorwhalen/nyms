"""The entity taxonomy: what kinds of things nyms detects, and how sensitive each is.

Three axes, following the terminology research (``docs/research/terminology-and-regulation.md``):
the **identifier class** (credential, direct identifier, quasi-identifier, sensitive attribute,
organisation identifier), a **tier** that says what the default policy does with it, and
**aliases** that map the type onto the names Presidio, Google DLP and HIPAA use, so a reader
coming from those tools finds their footing.

Tiers:

- ``0``: block. Credentials. Replaced always, whatever the policy says, unless a policy
  excludes the type explicitly.
- ``1``: replace by default. Direct identifiers of a natural person.
- ``2``: policy decides. Quasi-identifiers and sensitive attributes. The default policy
  replaces the ones that identify a party (organisation numbers and names, amounts) and keeps
  the ones the reader usually needs to reason (dates, postcodes, URLs), but reports them.

The registry is a plain dict so a caller can add a type (``ENTITY_TYPES['POLICY_NUMBER'] =
EntityType(...)``) before building detectors for it.

>>> ENTITY_TYPES['CPR'].tier, ENTITY_TYPES['DATE'].tier
(1, 2)
"""

from __future__ import annotations

from dataclasses import dataclass, field

CREDENTIAL = "credential"
DIRECT = "direct"
QUASI = "quasi"
SENSITIVE = "sensitive"
ORGANISATION = "organisation"


@dataclass(frozen=True)
class EntityType:
    """One entity type and its place in the taxonomy."""

    name: str
    identifier_class: str
    tier: int
    description: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


def _t(name, cls, tier, description, *aliases):
    return name, EntityType(name, cls, tier, description, tuple(aliases))


ENTITY_TYPES: dict[str, EntityType] = dict(
    [
        _t("CREDENTIAL", CREDENTIAL, 0, "API keys, tokens, passwords, private keys", "PASSWORD", "AWS_CREDENTIALS"),
        _t("PERSON", DIRECT, 1, "a natural person's name", "PERSON", "PERSON_NAME", "NAME"),
        _t("CPR", DIRECT, 1, "Danish personal identity number (personnummer)", "DENMARK_CPR_NUMBER", "SSN"),
        _t("EMAIL", DIRECT, 1, "e-mail address", "EMAIL_ADDRESS"),
        _t("PHONE", DIRECT, 1, "telephone number", "PHONE_NUMBER"),
        _t("ADDRESS", DIRECT, 1, "street address", "LOCATION", "STREET_ADDRESS"),
        _t("IBAN", DIRECT, 1, "international bank account number", "IBAN_CODE"),
        _t("BANK_ACCOUNT", DIRECT, 1, "Danish registreringsnummer and kontonummer", "BANK_ACCOUNT_NUMBER"),
        _t("CASE_ID", DIRECT, 1, "court case, journal or file number"),
        _t("CVR", ORGANISATION, 2, "Danish company registration number", "DENMARK_CVR_NUMBER", "VAT_NUMBER"),
        _t("ORG", ORGANISATION, 2, "organisation name", "ORGANIZATION", "NRP"),
        _t("AMOUNT", SENSITIVE, 2, "a monetary amount", "FINANCIAL"),
        _t("DATE", QUASI, 2, "a calendar date", "DATE_TIME"),
        _t("POSTCODE_CITY", QUASI, 2, "postcode and town", "LOCATION"),
        _t("URL", QUASI, 2, "a web address", "URL"),
    ]
)


#: The pseudo-type of a span that is one of the project's own surrogates. Such spans take
#: part in overlap resolution (so a surrogate is never re-detected as a name) and are then
#: dropped: a policy never acts on them.
SURROGATE_TYPE = "SURROGATE"


def tier_of(entity_type: str) -> int:
    """The tier of a type, ``2`` for an unregistered one (policy decides).

    >>> tier_of('CREDENTIAL'), tier_of('UNKNOWN')
    (0, 2)
    """
    et = ENTITY_TYPES.get(entity_type)
    return et.tier if et else 2
