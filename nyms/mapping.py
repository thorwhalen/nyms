"""The reversible mapping store: surrogate <-> original, per project, on a ``dol`` store.

A :class:`MappingStore` holds one :class:`Record` per distinct value: entity type, original,
normalised form, surrogate, aliases (other normalised forms that stand for the same value,
such as a surname alone), strategy name and creation time. It is keyed by surrogate (so
re-identification is one lookup) and indexes every normalised form in memory so the same
value gets the same surrogate on every occurrence and in every document of the project.

The backing store is any ``MutableMapping[str, dict]``. The default,
:func:`local_mapping_store`, is ``dol.JsonFiles`` under ``~/.local/share/nyms/<project>/mapping``,
one JSON file per record (file names are a URL-safe encoding of the surrogate, so any
surrogate string is a legal file name on any platform), which a human can inspect and
delete. Encryption at rest is the ``codec`` seam: pass :func:`encrypted` (needs the optional
``cryptography`` dependency) and every value is Fernet-encrypted under the project key before
it hits disk. The project directory carries a ``meta.json`` naming the codec, so opening an
encrypted store without the codec (or the reverse) fails with a clear message.

Normalisation decides what counts as "the same value": digits only for numeric identifiers,
casefolded and whitespace-collapsed for names, lower case for e-mail. The Danish genitive is
handled in :meth:`MappingStore.resolve`: ``Rasmus Jensens`` resolves to ``Rasmus Jensen``'s
surrogate plus the suffix ``s`` when that person is already known, and the facade writes
``[PERSON_1]s``. A first-seen ``...s`` is taken literally; if the base form turns up later,
the record is relinked to it.

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

import base64
import json
import re
import time
from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass, asdict, field
from pathlib import Path

from nyms.surrogates import Counter, Strategy

_DIGIT_TYPES = frozenset({"CPR", "CVR", "PHONE", "BANK_ACCOUNT"})
_ALNUM_UPPER_TYPES = frozenset({"IBAN", "CASE_ID"})
_LOWER_TYPES = frozenset({"EMAIL", "URL"})
_GENITIVE_SUFFIXES = ("'s", "’s", "s")
_NAME_TYPES = frozenset({"PERSON", "ORG"})


class StoreError(RuntimeError):
    """A mapping store could not be opened the way it was created (codec mismatch)."""


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


def canon(surrogate: str) -> str:
    """The loose form of a surrogate used for re-identification and collision checks.

    >>> canon('[ PERSON 1 ]'), canon('Alder  Brook')
    ('person_1', 'alder_brook')
    """
    s = surrogate.strip().strip("[]").casefold()
    return re.sub(r"[\s_\-]+", "_", s).strip("_")


@dataclass(frozen=True)
class Record:
    """One distinct value and its surrogate."""

    surrogate: str
    original: str
    entity_type: str
    normalised: str
    strategy: str = ""
    created: float = 0.0
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["aliases"] = list(self.aliases)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Record:
        return cls(
            **{
                k: d.get(k, "")
                for k in (
                    "surrogate",
                    "original",
                    "entity_type",
                    "normalised",
                    "strategy",
                )
            },
            created=float(d.get("created", 0.0)),
            aliases=tuple(d.get("aliases", ())),
        )


class MappingStore:
    """Records keyed by surrogate, with an in-memory index by ``(entity_type, normalised)``."""

    def __init__(
        self,
        store: MutableMapping[str, dict] | None = None,
        *,
        strategy: Strategy | None = None,
    ):
        self._store: MutableMapping[str, dict] = {} if store is None else store
        self.strategy: Strategy = Counter() if strategy is None else strategy
        self._reload()

    def _reload(self) -> None:
        self._by_value: dict[tuple[str, str], str] = {}
        self._counts: dict[str, int] = {}
        self._canons: dict[str, str] = {}
        for surrogate in list(self._store):
            self._index(Record.from_dict(self._store[surrogate]))
        self._n_loaded = len(self._store)

    def _index(self, rec: Record) -> None:
        self._by_value[(rec.entity_type, rec.normalised)] = rec.surrogate
        for a in rec.aliases:
            self._by_value.setdefault((rec.entity_type, a), rec.surrogate)
        self._counts[rec.entity_type] = self._counts.get(rec.entity_type, 0) + 1
        self._canons[canon(rec.surrogate)] = rec.surrogate

    def _refresh_if_changed(self) -> None:
        """Another process may have written records since we loaded; pick them up on a miss."""
        if len(self._store) != self._n_loaded:
            self._reload()

    # -- Vault protocol -------------------------------------------------------
    def __contains__(self, surrogate: object) -> bool:
        return surrogate in self._store or (
            isinstance(surrogate, str) and canon(surrogate) in self._canons
        )

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
        not guess that an unknown ``...s`` is a genitive; if the base form appears later the
        record is relinked to it.
        """
        norm = normalise(entity_type, text)
        existing = self._by_value.get((entity_type, norm))
        if existing is None:
            self._refresh_if_changed()
            existing = self._by_value.get((entity_type, norm))
        if existing is not None:
            return existing, ""
        if entity_type in _NAME_TYPES:
            for suffix in _GENITIVE_SUFFIXES:
                if norm.endswith(suffix) and len(norm) > len(suffix) + 1:
                    base = self._by_value.get((entity_type, norm[: -len(suffix)]))
                    if base is not None:
                        return base, text[-len(suffix) :]
                genitive = self._by_value.get((entity_type, norm + suffix))
                if genitive is not None:
                    self._relink(genitive, entity_type, text.strip(), norm)
                    return genitive, ""
        return self.add(entity_type, text), ""

    def _relink(
        self, surrogate: str, entity_type: str, original: str, norm: str
    ) -> None:
        """A known genitive form turned out to have a base form: the base is the original."""
        rec = self.record(surrogate)
        if rec is None:
            return
        new = Record(
            surrogate,
            original,
            entity_type,
            norm,
            rec.strategy,
            rec.created,
            tuple(sorted({*rec.aliases, rec.normalised})),
        )
        self._store[surrogate] = new.to_dict()
        self._by_value[(entity_type, norm)] = surrogate

    def add(self, entity_type: str, text: str, *, surrogate: str | None = None) -> str:
        """Create a record for a new value (with a given *surrogate*, or one from the strategy)."""
        norm = normalise(entity_type, text)
        if (entity_type, norm) in self._by_value:
            return self._by_value[(entity_type, norm)]
        if surrogate is None:
            surrogate = self.strategy(entity_type, text.strip(), vault=self)
        if surrogate in self._store or canon(surrogate) in self._canons:
            raise ValueError(
                f"surrogate already in use (or indistinguishable from one): {surrogate!r}"
            )
        rec = Record(
            surrogate,
            text.strip(),
            entity_type,
            norm,
            type(self.strategy).__name__,
            time.time(),
        )
        self._store[surrogate] = rec.to_dict()
        self._index(rec)
        self._n_loaded = len(self._store)
        return surrogate

    def alias(self, entity_type: str, text: str, surrogate: str) -> str:
        """Choose the surrogate for a value yourself (before it is first seen)."""
        return self.add(entity_type, text, surrogate=surrogate)

    def add_alias_form(self, surrogate: str, entity_type: str, text: str) -> None:
        """Make *text* (a surname alone, say) resolve to an existing record's surrogate."""
        rec = self.record(surrogate)
        norm = normalise(entity_type, text)
        if rec is None or (entity_type, norm) in self._by_value:
            return
        new = Record(
            rec.surrogate,
            rec.original,
            rec.entity_type,
            rec.normalised,
            rec.strategy,
            rec.created,
            tuple(sorted({*rec.aliases, norm})),
        )
        self._store[surrogate] = new.to_dict()
        self._by_value[(entity_type, norm)] = surrogate

    def to_dict(self) -> dict[str, str]:
        """``{surrogate: original}``. This is the sensitive artefact; handle it as such."""
        return {r.surrogate: r.original for r in self.records()}


def project_dir(project: str, *, rootdir: str | Path | None = None) -> Path:
    """Where a project's data lives: ``<rootdir or ~/.local/share/nyms>/<project>``."""
    from nyms.keys import data_dir, _check_project_name

    _check_project_name(project)
    return (Path(rootdir) if rootdir else data_dir()) / project


def _safe_id(surrogate: str) -> str:
    return (
        base64.urlsafe_b64encode(surrogate.encode("utf-8")).decode("ascii").rstrip("=")
    )


def _surrogate_of_id(file_id: str) -> str:
    return base64.urlsafe_b64decode(file_id + "=" * (-len(file_id) % 4)).decode("utf-8")


def local_mapping_store(
    project: str = "default", *, rootdir: str | Path | None = None, codec=None
) -> MutableMapping[str, dict]:
    """A ``dol`` file store of records under the project dir, optionally through *codec*.

    *codec* is a pair ``(encode: bytes -> bytes, decode: bytes -> bytes)`` applied to the JSON
    bytes of each record; see :func:`encrypted`. The project's ``meta.json`` records which
    codec the store was created with; a mismatch raises :class:`StoreError`.
    """
    import dol

    pdir = project_dir(project, rootdir=rootdir)
    path = pdir / "mapping"
    path.mkdir(parents=True, exist_ok=True)
    for d in (pdir, path):
        try:
            d.chmod(0o700)
        except OSError:
            pass
    codec_name = "none" if codec is None else getattr(codec, "name", "custom")
    meta = pdir / "meta.json"
    if meta.exists():
        recorded = json.loads(meta.read_text("utf-8")).get("codec", "none")
        if recorded != codec_name:
            raise StoreError(
                f"project {project!r} was created with codec {recorded!r} but is being opened with {codec_name!r}; "
                + (
                    "pass encrypt=True / --encrypt"
                    if recorded == "fernet"
                    else "open it without encryption"
                )
            )
    else:
        meta.write_text(json.dumps({"codec": codec_name, "nyms": 1}), "utf-8")
    files = dol.Files(str(path))
    if codec is None:
        encode, decode = (lambda b: b), (lambda b: b)
    else:
        encode, decode = codec
    return dol.wrap_kvs(
        files,
        id_of_key=_safe_id,
        key_of_id=_surrogate_of_id,
        data_of_obj=lambda obj: encode(
            json.dumps(obj, ensure_ascii=False).encode("utf-8")
        ),
        obj_of_data=lambda data: json.loads(decode(data).decode("utf-8")),
    )


class _Codec(tuple):
    """An ``(encode, decode)`` pair with a name, for the ``meta.json`` marker."""

    name = "custom"


def encrypted(key: bytes):
    """A ``(encode, decode)`` codec: Fernet under a key derived from *key*. Needs ``cryptography``.

    Fernet (AES-128-CBC with HMAC-SHA-256) is the simplest authenticated encryption the
    ``cryptography`` package offers; AES-GCM or ``age`` are the replacements.
    """
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "encryption at rest needs the optional dependency: pip install 'nyms[crypto]'"
        ) from e
    import hashlib

    fkey = base64.urlsafe_b64encode(hashlib.sha256(b"nyms-store\x00" + key).digest())
    f = Fernet(fkey)

    class Fernet_(_Codec):
        name = "fernet"

    return Fernet_((f.encrypt, f.decrypt))
