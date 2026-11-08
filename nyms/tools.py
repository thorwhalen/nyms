"""The SSOT of operations: plain functions, JSON-able in and out, surface-agnostic.

The CLI (``nyms.__main__``, via ``cw``) dispatches this module's ``_dispatch_funcs``; an MCP
server (``py2mcp.mk_mcp_from_refs(['nyms.tools:pseudonymise', ...])``) or an HTTP adapter would
reference the same names. Nothing here prints or exits; nothing imports a surface.

A *source* argument is a path to a file (read as UTF-8), ``-`` for stdin, or the text itself.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from nyms.core import Pseudonymiser
from nyms.policy import Policy
from nyms.surrogates import Aliases, Counter, KeyedWords, RandomWords, readable as _readable

POLICIES = {"default": Policy.default, "identifiers": Policy.identifiers, "strict": Policy.strict}
STRATEGIES = ("counter", "keyed-words", "random-words")


def _read_source(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    if len(source) < 4096 and os.path.exists(source):
        return Path(source).read_text("utf-8")
    return source


def _split(csv: str) -> list[str]:
    return [x.strip() for x in csv.split(",") if x.strip()] if csv else []


def _pseudonymiser(project: str, *, policy: str = "default", names: str = "", strategy: str = "counter", encrypt: bool = False, aliases: str = "") -> Pseudonymiser:
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}; one of {sorted(POLICIES)}")
    pol = POLICIES[policy]()
    name_list = _split(names)
    if name_list:
        pol = pol.with_names(*name_list)
    p = Pseudonymiser(project, policy=pol, names=name_list, encrypt=encrypt, strategy=Counter())
    strat = _strategy(strategy, p.key)
    alias_pairs = dict(x.split("=", 1) for x in _split(aliases) if "=" in x)
    p.mapping.strategy = Aliases(alias_pairs, fallback=strat) if alias_pairs else strat
    return p


def _strategy(name: str, key: bytes):
    if name == "counter":
        return Counter()
    if name == "keyed-words":
        return KeyedWords(key)
    if name == "random-words":
        return RandomWords()
    raise ValueError(f"unknown strategy {name!r}; one of {STRATEGIES}")


def _emit(text: str, out: str | None) -> dict:
    if out:
        Path(out).write_text(text, "utf-8")
        return {"out": out, "chars": len(text)}
    return {"text": text}


def pseudonymise(source: str, *, project: str = "default", out: str | None = None, policy: str = "default", names: str = "", strategy: str = "counter", aliases: str = "", encrypt: bool = False) -> dict:
    """Replace detected identifiers in *source* with surrogates; the project's mapping remembers them.

    *names*: comma-separated names you already know (the parties). *aliases*: ``Name=Alias,...``
    surrogates you choose yourself. *strategy*: ``counter`` (``[PERSON_1]``), ``keyed-words``
    or ``random-words``. The result carries the text (or the ``out`` path) and the run report.
    """
    p = _pseudonymiser(project, policy=policy, names=names, strategy=strategy, encrypt=encrypt, aliases=aliases)
    r = p.pseudonymise(_read_source(source))
    return {**_emit(r.text, out), "report": r.report}


def reidentify(source: str, *, project: str = "default", out: str | None = None, encrypt: bool = False) -> dict:
    """Put the originals back into *source* (an AI's answer, say). Lists tokens it could not place."""
    p = Pseudonymiser(project, encrypt=encrypt)
    r = p.reidentify(_read_source(source))
    return {**_emit(r.text, out), "restored": r.restored, "unmatched": r.unmatched}


def detect(source: str, *, names: str = "", policy: str = "default") -> list[dict]:
    """The spans the deterministic pass finds, with the policy's decision for each. Nothing is stored."""
    pol = POLICIES[policy]()
    p = Pseudonymiser("detect-only", store={}, policy=pol, names=_split(names))
    return [{**s.to_dict(), "action": "replace" if pol.accepts(s) else "keep"} for s in p.detect(_read_source(source))]


def check(source: str, *, project: str = "default", encrypt: bool = False) -> dict:
    """Originals of *project* that occur in *source*: what would leak if this text were sent."""
    p = Pseudonymiser(project, encrypt=encrypt)
    leaks = p.check(_read_source(source))
    return {"ok": not leaks, "leaks": leaks}


def mapping(project: str = "default", *, encrypt: bool = False) -> list[dict]:
    """The project's records (surrogate, original, type). Sensitive: this is the key to the text."""
    p = Pseudonymiser(project, encrypt=encrypt)
    return [r.to_dict() for r in p.mapping.records()]


def readable(value: str, *, project: str = "default", entity_type: str = "VALUE", n_words: int = 2) -> str:
    """A keyed hash of *value* under the project's key, rendered as readable words."""
    return _readable(value, key=Pseudonymiser(project, store={}).key, entity_type=entity_type, n_words=n_words)


def policies() -> dict:
    """The policy presets and the entity types each replaces."""
    return {name: sorted(make().include or []) or "all detected" for name, make in POLICIES.items()}


_dispatch_funcs = [pseudonymise, reidentify, detect, check, mapping, readable, policies]
