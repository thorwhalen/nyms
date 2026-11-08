"""Surrogate (pseudonym) generation: what replaces a detected value.

A **surrogate strategy** is a callable ``(entity_type, value, *, vault) -> str`` that returns
the replacement for a value seen for the first time; the mapping store calls it once per new
value and remembers the answer, so every later occurrence gets the same surrogate. ``vault``
is the store itself, exposing ``__contains__`` (is this surrogate taken?) and
``count(entity_type)``, which is all a strategy needs to avoid collisions or number things.

Four strategies, matching the surrogate research (``docs/research/surrogates-crypto-and-keys.md``):

- :class:`Counter`: ``[PERSON_1]``, ``[CPR_2]``. The default. Bracketed typed tokens were
  the form LLMs altered least in the one benchmark found, and the counter is per project
  (persisted with the store), so the same person is ``[PERSON_1]`` in every document.
- :class:`KeyedWords`: HMAC-SHA-256 of the value under a secret key, rendered as readable
  words from a word list (``[PERSON:alder-brook]``, or name-shaped ``Alder Brook``). The
  same key gives the same surrogate on any machine without sharing a store, which is the
  property the vault lacks. Never unkeyed: a plain hash of a CPR number falls to enumeration.
- :class:`RandomWords`: readable words from random bytes. A classic tokenisation vault.
- :class:`Aliases`: the user's own choice for some values ("call the landlord Mr Green"),
  with any other strategy as the fallback.

The rendering of bytes to words (:func:`words_from_bytes`) is separate from where the bytes
come from, and is the tool the user asked for ("a cryptographic hash mapped to a sequence of
letters that is actually readable"). It also stands alone:

>>> words_from_bytes(b'\\x00' * 8, n=2)
['aardvark', 'aardvark']
>>> Counter()('PERSON', 'Hans Jensen', vault=_EmptyVault())
'[PERSON_1]'
>>> KeyedWords(b'k' * 32)('CPR', '010190-1234', vault=_EmptyVault())
'[CPR:...]'
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from typing import Protocol, runtime_checkable


@runtime_checkable
class Vault(Protocol):
    """What a strategy may ask of the mapping store."""

    def __contains__(self, surrogate: object) -> bool: ...

    def count(self, entity_type: str) -> int: ...


class _EmptyVault:
    def __contains__(self, surrogate):
        return False

    def count(self, entity_type):
        return 0


Strategy = Callable[..., str]  # (entity_type, value, *, vault) -> str


# --------------------------------------------------------------------------- rendering


@lru_cache(maxsize=None)
def default_wordlist() -> tuple[str, ...]:
    """The bundled EFF short wordlist 2.0: 1,296 common words with unique 3-letter prefixes.

    >>> len(default_wordlist())
    1296
    """
    text = resources.files("nyms.data.wordlists").joinpath("eff_short_wordlist_2_0.txt").read_text("utf-8")
    return tuple(line.split("\t")[-1].strip() for line in text.splitlines() if line.strip())


def words_from_bytes(data: bytes, *, n: int = 2, wordlist: Sequence[str] | None = None) -> list[str]:
    """Render *data* as *n* words from *wordlist* (default: the EFF short list).

    The integer value of the bytes is written in base ``len(wordlist)``; the lowest *n*
    digits become words. Each word of the default list carries log2(1296) = 10.3 bits, so
    two words identify about 1.7 million values and three about 2.2 billion.

    >>> words_from_bytes(bytes([0, 0, 0, 1]), n=2)
    ['aardvark', 'abandoned']
    """
    words = default_wordlist() if wordlist is None else wordlist
    base = len(words)
    value = int.from_bytes(data, "big")
    out = []
    for _ in range(n):
        value, idx = divmod(value, base)
        out.append(words[idx])
    out.reverse()  # most significant word first, so it reads like a number
    return out


_CONSONANTS = "bdfgklmnprstvz"
_VOWELS = "aeiou"


def syllables_from_bytes(data: bytes, *, n: int = 3) -> str:
    """Render *data* as a pronounceable made-up word of *n* consonant-vowel syllables.

    Needs no word list and never collides with a dictionary word, at the cost of looking
    invented. 70 syllables, about 6.1 bits each.

    >>> syllables_from_bytes(b'\\x00\\x00\\x00', n=3)
    'bababa'
    """
    value = int.from_bytes(data, "big")
    out = []
    for _ in range(n):
        value, idx = divmod(value, len(_CONSONANTS) * len(_VOWELS))
        c, v = divmod(idx, len(_VOWELS))
        out.append(_CONSONANTS[c] + _VOWELS[v])
    return "".join(out)


def keyed_digest(key: bytes, entity_type: str, value: str) -> bytes:
    """HMAC-SHA-256 of ``entity_type || NUL || value`` under *key*.

    The type is part of the message so a person and a company with the same string get
    different surrogates. The key must be secret: with a public key this is an unkeyed hash
    and a low-entropy identifier (a CPR number, a phone number) is recovered by enumeration.
    """
    if len(key) < 16:
        raise ValueError("key must be at least 16 bytes")
    return hmac.new(key, f"{entity_type}\x00{value}".encode("utf-8"), hashlib.sha256).digest()


# --------------------------------------------------------------------------- strategies


@dataclass
class Counter:
    """``[PERSON_1]``-style typed counters, numbered per entity type within the project."""

    template: str = "[{type}_{n}]"

    def __call__(self, entity_type: str, value: str, *, vault: Vault) -> str:
        n = vault.count(entity_type) + 1
        while (s := self.template.format(type=entity_type, n=n)) in vault:
            n += 1
        return s


#: Templates per entity type for word surrogates. ``{words}`` is hyphen-joined lower case,
#: ``{Words}`` is capitalised and space-joined (name-shaped), ``{type}`` the entity type.
DEFAULT_WORD_TEMPLATES: dict[str, str] = {"PERSON": "{Words}", "ORG": "{Words}"}
DEFAULT_WORD_TEMPLATE = "[{type}:{words}]"


def _render(template: str, entity_type: str, words: Sequence[str]) -> str:
    return template.format(
        type=entity_type,
        words="-".join(words),
        Words=" ".join(w.capitalize() for w in words),
        joined="".join(words),
    )


@dataclass
class KeyedWords:
    """Keyed hash (HMAC-SHA-256) rendered as readable words. Deterministic under one key."""

    key: bytes
    n_words: int = 2
    wordlist: Sequence[str] | None = None
    templates: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_WORD_TEMPLATES))
    default_template: str = DEFAULT_WORD_TEMPLATE

    def __call__(self, entity_type: str, value: str, *, vault: Vault) -> str:
        digest = keyed_digest(self.key, entity_type, value)
        template = self.templates.get(entity_type, self.default_template)
        n = self.n_words
        while True:
            s = _render(template, entity_type, words_from_bytes(digest, n=n, wordlist=self.wordlist))
            if s not in vault:
                return s
            n += 1  # a collision with another value: one more word disambiguates


@dataclass
class RandomWords:
    """Random readable words (a tokenisation vault): no key, no information about the value."""

    n_words: int = 2
    wordlist: Sequence[str] | None = None
    templates: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_WORD_TEMPLATES))
    default_template: str = DEFAULT_WORD_TEMPLATE

    def __call__(self, entity_type: str, value: str, *, vault: Vault) -> str:
        template = self.templates.get(entity_type, self.default_template)
        while True:
            s = _render(template, entity_type, words_from_bytes(secrets.token_bytes(16), n=self.n_words, wordlist=self.wordlist))
            if s not in vault:
                return s


@dataclass
class Aliases:
    """The user's own surrogates for some values; *fallback* for the rest.

    Keys are compared casefolded and whitespace-collapsed.

    >>> a = Aliases({'Hans Jensen': 'Mr Green'}, fallback=Counter())
    >>> a('PERSON', 'hans  jensen', vault=_EmptyVault()), a('PERSON', 'Else Berg', vault=_EmptyVault())
    ('Mr Green', '[PERSON_1]')
    """

    aliases: Mapping[str, str]
    fallback: Strategy = field(default_factory=Counter)

    def __post_init__(self):
        self._lookup = {" ".join(k.casefold().split()): v for k, v in self.aliases.items()}

    def __call__(self, entity_type: str, value: str, *, vault: Vault) -> str:
        return self._lookup.get(" ".join(value.casefold().split())) or self.fallback(entity_type, value, vault=vault)


def readable(value: str, *, key: bytes, entity_type: str = "VALUE", n_words: int = 2, wordlist: Sequence[str] | None = None) -> str:
    """The stand-alone tool: a keyed hash of *value*, as readable words.

    >>> readable('010190-1234', key=b'0' * 32) == readable('010190-1234', key=b'0' * 32)
    True
    >>> readable('010190-1234', key=b'0' * 32) != readable('010190-1234', key=b'1' * 32)
    True
    """
    return "-".join(words_from_bytes(keyed_digest(key, entity_type, value), n=n_words, wordlist=wordlist))
