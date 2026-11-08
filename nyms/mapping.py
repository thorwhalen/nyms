"""The reversible mapping store: surrogate <-> original, per project, on a ``dol`` store.

A :class:`MappingStore` holds one :class:`Record` per distinct value: entity type, original,
normalised form, surrogate, strategy name and creation time. It is keyed by surrogate (so
re-identification is one lookup) and indexes ``(entity_type, normalised)`` in memory so the
same value gets the same surrogate on every occurrence and in every document of the project.

The backing store is any ``MutableMapping[str, dict]``. The default,
:func:`local_mapping_store`, is ``dol.JsonFiles`` under ``~/.local/share/nyms/<project>/mapping``,
one JSON file per record, which a ``git``-free human can inspect and delete. Encryption at
rest is the ``codec`` seam: pass :func:`encrypted` (needs the optional ``cryptography``
dependency) and every value is Fernet-encrypted under the project key before it hits disk.

Normalisation decides what counts as "the same value": digits only for numeric identifiers,
casefolded and whitespace-collapsed for names, lower case for e-mail. The Danish genitive is
handled in :meth:`MappingStore.resolve`: ``Rasmus Jensens`` resolves to ``Rasmus Jensen``'s
surrogate plus the suffix ``s`` when that person is already known, and the facade writes
``[PERSON_1]s``.

>>> from nyms.surrogates import Counter
>>> m = MappingStore({}, strategy=Counter())
>>> m.resolve('PERSON', 'Rasmus Jensen')
('[PERSON_1]', '')
>>> m.resolve('PERSON', 'Rasmus Jensens')
('[PERSON_1]', 's')
>>> m.resolve('CPR', '010190 1234') == m.resolve('CPR', '010190-1234')
True
>>> m.original('[PERSON_1]')
'Rasmus Jensen'
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass, asdict
from pathlib import Path

from nyms.surrogates import Counter, Strategy

_DIGIT_TYPES = frozenset({"CPR", "CVR", "PHONE", "BANK_ACCOUNT"})
_ALNUM_UPPER_TYPES = frozenset({"IBAN", "CASE_ID"})
_LOWER_TYPES = frozenset({"EMAIL", "URL"})
_GENITIVE_SUFFIXES = ("'s", "’s", "s")


def normalise(entity_type: str, text: str) -> str:
    """The identity of a value for the purpose of "same surrogate".

    >>> normalise('CPR', '010190-1234'), normalise('PERSON', ' Hans   JENSEN '), normalise('EMAIL', 'A@B.dk')
    ('0101901234', 'hans jensen', 'a@b.dk')
    """
    if entity_type in _DIGIT_TYPES:
        return re.sub(r"\D", "", text)
    if entity_type in _ALNUM_UPPER_TYPES:
        return re.sub(r"[^0-9A-Za-z/]", "", text).upper()
    if entity_type in _LOWER_TYPES:
        return text.strip().lower()
    return " ".join(text.casefold().split()).strip(" .,;:")


@dataclass(frozen=True)
class Record:
    """One distinct value and its surrogate."""

    surrogate: str
    original: str
    entity_type: str
    normalised: str
    strategy: str = ""
    created: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Record:
        return cls(**{k: d.get(k, "") for k in ("surrogate", "original", "entity_type", "normalised", "strategy")}, created=float(d.get("created", 0.0)))


class MappingStore:
    """Records keyed by surrogate, with an in-memory index by ``(entity_type, normalised)``."""

    def __init__(self, store: MutableMapping[str, dict] | None = None, *, strategy: Strategy | None = None):
        self._store: MutableMapping[str, dict] = {} if store is None else store
        self.strategy: Strategy = Counter() if strategy is None else strategy
        self._by_value: dict[tuple[str, str], str] = {}
        self._counts: dict[str, int] = {}
        for surrogate in list(self._store):
            rec = Record.from_dict(self._store[surrogate])
            self._by_value[(rec.entity_type, rec.normalised)] = surrogate
            self._counts[rec.entity_type] = self._counts.get(rec.entity_type, 0) + 1

    # -- Vault protocol -------------------------------------------------------
    def __contains__(self, surrogate: object) -> bool:
        return surrogate in self._store

    def count(self, entity_type: str) -> int:
        return self._counts.get(entity_type, 0)

    def __len__(self) -> int:
        return len(self._store)

    def __iter__(self) -> Iterator[str]:
        return iter(self._store)

    # -- lookups --------------------------------------------------------------
    def record(self, surrogate: str) -> Record | None:
        d = self._store.get(surrogate)
        return Record.from_dict(d) if d is not None else None

    def original(self, surrogate: str) -> str | None:
        rec = self.record(surrogate)
        return rec.original if rec else None

    def surrogate_of(self, entity_type: str, text: str) -> str | None:
        return self._by_value.get((entity_type, normalise(entity_type, text)))

    def records(self) -> Iterator[Record]:
        for s in list(self._store):
            yield Record.from_dict(self._store[s])

    # -- the one write path ---------------------------------------------------
    def resolve(self, entity_type: str, text: str) -> tuple[str, str]:
        """``(surrogate, suffix)`` for *text*, creating the surrogate if the value is new.

        *suffix* is a genitive ending found on an already known value, to be re-attached
        after the surrogate (``[PERSON_1]`` + ``s``). It is empty for a new value: nyms does
        not guess that an unknown ``...s`` is a genitive.
        """
        norm = normalise(entity_type, text)
        existing = self._by_value.get((entity_type, norm))
        if existing is not None:
            return existing, ""
        if entity_type == "PERSON" or entity_type == "ORG":
            for suffix in _GENITIVE_SUFFIXES:
                if norm.endswith(suffix) and len(norm) > len(suffix) + 1:
                    base = self._by_value.get((entity_type, norm[: -len(suffix)]))
                    if base is not None:
                        return base, text[-len(suffix):]
        return self.add(entity_type, text), ""

    def add(self, entity_type: str, text: str, *, surrogate: str | None = None) -> str:
        """Create a record for a new value (with a given *surrogate*, or one from the strategy)."""
        norm = normalise(entity_type, text)
        if (entity_type, norm) in self._by_value:
            return self._by_value[(entity_type, norm)]
        if surrogate is None:
            surrogate = self.strategy(entity_type, text.strip(), vault=self)
        if surrogate in self._store:
            raise ValueError(f"surrogate already in use: {surrogate!r}")
        rec = Record(surrogate, text.strip(), entity_type, norm, type(self.strategy).__name__, time.time())
        self._store[surrogate] = rec.to_dict()
        self._by_value[(entity_type, norm)] = surrogate
        self._counts[entity_type] = self._counts.get(entity_type, 0) + 1
        return surrogate

    def alias(self, entity_type: str, text: str, surrogate: str) -> str:
        """Choose the surrogate for a value yourself (before it is first seen)."""
        return self.add(entity_type, text, surrogate=surrogate)

    def to_dict(self) -> dict[str, str]:
        """``{surrogate: original}``. This is the sensitive artefact; handle it as such."""
        return {r.surrogate: r.original for r in self.records()}


def project_dir(project: str, *, rootdir: str | Path | None = None) -> Path:
    """Where a project's data lives: ``<rootdir or ~/.local/share/nyms>/<project>``."""
    from nyms.keys import data_dir, _check_project_name

    _check_project_name(project)
    return (Path(rootdir) if rootdir else data_dir()) / project


def local_mapping_store(project: str = "default", *, rootdir: str | Path | None = None, codec=None) -> MutableMapping[str, dict]:
    """A ``dol.JsonFiles`` store of records under the project dir, optionally through *codec*.

    *codec* is a pair ``(encode: bytes -> bytes, decode: bytes -> bytes)`` applied to the JSON
    bytes of each record; see :func:`encrypted`.
    """
    import dol

    path = project_dir(project, rootdir=rootdir) / "mapping"
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    if codec is None:
        return dol.JsonFiles(str(path))
    encode, decode = codec
    files = dol.Files(str(path))
    return dol.wrap_kvs(
        files,
        data_of_obj=lambda obj: encode(json.dumps(obj, ensure_ascii=False).encode("utf-8")),
        obj_of_data=lambda data: json.loads(decode(data).decode("utf-8")),
    )


def encrypted(key: bytes):
    """A ``(encode, decode)`` codec: Fernet under a key derived from *key*. Needs ``cryptography``.

    Fernet (AES-128-CBC with HMAC-SHA-256) is the simplest authenticated encryption the
    ``cryptography`` package offers; AES-GCM or ``age`` are the replacements.
    """
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:  # pragma: no cover
        raise ImportError("encryption at rest needs the optional dependency: pip install 'nyms[crypto]'") from e
    import base64
    import hashlib

    fkey = base64.urlsafe_b64encode(hashlib.sha256(b"nyms-store\x00" + key).digest())
    f = Fernet(fkey)
    return f.encrypt, f.decrypt
