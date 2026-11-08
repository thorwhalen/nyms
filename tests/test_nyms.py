"""Tests for nyms: fixtures (Danish, English, credentials), leakage, round trip, consistency."""

import json
import re
from pathlib import Path

import pytest

from nyms import (
    Aliases,
    Counter,
    KeyedWords,
    MappingStore,
    Policy,
    Pseudonymiser,
    RandomWords,
    detect,
    normalise,
    readable,
    words_from_bytes,
)
from nyms.detect import cpr_mod11_ok, cvr_ok, iban_ok
from nyms.mapping import encrypted, local_mapping_store

FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text("utf-8"))
KNOWN_NAMES = ["Rasmus Østergaard Jensen", "Eleanor Whitfield"]


def _compact(entity_type_hint: str, s: str) -> str:
    return normalise(entity_type_hint, s)


@pytest.mark.parametrize("fixture", sorted(EXPECTED))
def test_fixture_leakage_and_coverage(fixture):
    text = (FIXTURES / fixture).read_text("utf-8")
    p = Pseudonymiser(store={}, names=KNOWN_NAMES)
    result = p.pseudonymise(text)
    out = result.text
    for value in EXPECTED[fixture]["must_replace"]:
        assert value in text, f"fixture {fixture} lacks {value!r}"
        assert value not in out, f"{value!r} leaked in {fixture}"
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 8:
            assert digits not in re.sub(r"\D", "", out), f"digits of {value!r} leaked in {fixture}"
    detected = {s.text for s in result.replaced} | {s.text for s in result.kept}
    for value in EXPECTED[fixture]["must_detect_kept"]:
        assert any(value in d or d in value for d in detected), f"{value!r} not detected in {fixture}"
        assert value in out, f"{value!r} should have been kept by the default policy"
    assert result.report["caveat"]


@pytest.mark.parametrize("fixture", sorted(EXPECTED))
def test_round_trip_restores_every_original(fixture):
    text = (FIXTURES / fixture).read_text("utf-8")
    p = Pseudonymiser(store={}, names=KNOWN_NAMES)
    result = p.pseudonymise(text)
    back = p.reidentify(result.text)
    assert back.unmatched == []
    assert back.restored == len(result.replacements)
    for span, _ in result.replacements:
        assert span.text in back.text
    assert p.check(result.text) == []
    assert p.check(text) != []


def test_strict_policy_replaces_dates_and_round_trips():
    text = (FIXTURES / "da_lejesag.md").read_text("utf-8")
    p = Pseudonymiser(store={}, policy=Policy.strict(), names=KNOWN_NAMES)
    r = p.pseudonymise(text)
    assert "15. marts 2024" not in r.text
    assert p.reidentify(r.text).text == text or p.check(r.text) == []


def test_same_person_same_surrogate_across_documents_and_genitive():
    store = {}
    p = Pseudonymiser(store=store)
    a = p.pseudonymise("Rasmus Jensen skrev.")
    b = Pseudonymiser(store=store).pseudonymise("Rasmus Jensens svar. RASMUS JENSEN igen.")
    assert a.text == "[PERSON_1] skrev."
    assert b.text == "[PERSON_1]s svar. [PERSON_1] igen."


def test_two_people_one_surname_get_two_surrogates():
    p = Pseudonymiser(store={})
    r = p.pseudonymise("Hans Jensen og Mette Jensen mødtes.")
    assert r.text == "[PERSON_1] og [PERSON_2] mødtes."


def test_tolerant_reidentification_and_prefix_safety():
    p = Pseudonymiser(store={})
    for i in range(1, 12):
        p.mapping.add("PERSON", f"Person Nummer{i}")
    assert p.mapping.surrogate_of("PERSON", "Person Nummer11") == "[PERSON_11]"
    r = p.reidentify("[PERSON_11] og [person 1] og PERSON_2 og [ PERSON-3 ]s og [PERSON_99]")
    assert r.text == "Person Nummer11 og Person Nummer1 og Person Nummer2 og Person Nummer3s og [PERSON_99]"
    assert r.unmatched == ["[PERSON_99]"]
    assert r.restored == 4


def test_aliases_and_known_names():
    strategy = Aliases({"Vesterbro Ejendomme ApS": "the landlord"}, fallback=Counter())
    p = Pseudonymiser(store={}, strategy=strategy, names=["Vesterbro Ejendomme ApS"], policy=Policy.default().with_names("Vesterbro Ejendomme ApS"))
    r = p.pseudonymise("Vesterbro Ejendomme ApS afviste kravet.")
    assert r.text == "the landlord afviste kravet."
    assert p.reidentify("Svar til the landlord.").text == "Svar til Vesterbro Ejendomme ApS."


def test_keyed_words_deterministic_per_key_and_type():
    k1, k2 = b"a" * 32, b"b" * 32
    s1 = KeyedWords(k1)("CPR", "010190-1234", vault=MappingStore({}))
    assert s1 == KeyedWords(k1)("CPR", "010190-1234", vault=MappingStore({}))
    assert s1 != KeyedWords(k2)("CPR", "010190-1234", vault=MappingStore({}))
    assert s1 != KeyedWords(k1)("PHONE", "010190-1234", vault=MappingStore({}))
    assert re.fullmatch(r"\[CPR:[a-z]+-[a-z]+\]", s1)
    person = KeyedWords(k1)("PERSON", "Hans Jensen", vault=MappingStore({}))
    assert re.fullmatch(r"[A-Z][a-z]+ [A-Z][a-z]+", person)
    assert readable("x", key=k1) == readable("x", key=k1) and "-" in readable("x", key=k1)


def test_word_surrogates_round_trip_through_tolerant_matcher():
    p = Pseudonymiser(store={}, strategy=KeyedWords(b"k" * 32))
    r = p.pseudonymise("Rasmus Jensen (CPR 010190-1234) ringede.")
    back = p.reidentify(r.text.lower())
    assert "Rasmus Jensen" in back.text and "010190-1234" in back.text


def test_random_words_unique():
    vault = MappingStore({}, strategy=RandomWords())
    seen = {vault.add("PERSON", f"P{i}") for i in range(50)}
    assert len(seen) == 50


def test_words_from_bytes_bits():
    assert words_from_bytes(bytes([0, 0, 0, 1]), n=2) == ["aardvark", "abandoned"]
    assert len(set(words_from_bytes(bytes(range(32)), n=3))) >= 2


def test_validators():
    assert cpr_mod11_ok("211062-5629") and not cpr_mod11_ok("010190-1234")
    assert cvr_ok("10150817") and not cvr_ok("12345678")
    assert iban_ok("GB29 NWBK 6016 1331 9268 19") and not iban_ok("GB29 NWBK 6016 1331 9268 18")


def test_cpr_without_mod11_is_still_detected():
    spans = detect("Personnummer 010190-1234 er ikke mod-11-gyldigt.")
    assert [(s.entity_type, s.text) for s in spans] == [("CPR", "010190-1234")]


def test_policy_identifiers_keeps_amounts():
    p = Pseudonymiser(store={}, policy=Policy.identifiers())
    r = p.pseudonymise("Beløb: 12.500 kr. til Hans Jensen.")
    assert "12.500 kr." in r.text and "[PERSON_1]" in r.text
    assert any(k.entity_type == "AMOUNT" for k in r.kept)


def test_policy_serialises():
    pol = Policy.default().with_names("Acme ApS")
    assert Policy.from_dict(pol.to_dict()) == pol


def test_local_store_persists_and_encrypts(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    pytest.importorskip("cryptography")
    key = b"z" * 32
    store = local_mapping_store("proj", rootdir=tmp_path, codec=encrypted(key))
    p = Pseudonymiser("proj", store=store, key=key)
    p.pseudonymise("Hans Jensen, 12 34 56 78")
    raw = b"".join(f.read_bytes() for f in (tmp_path / "proj" / "mapping").iterdir())
    assert b"Jensen" not in raw
    again = Pseudonymiser("proj", store=local_mapping_store("proj", rootdir=tmp_path, codec=encrypted(key)), key=key)
    assert again.reidentify("[PERSON_1]").text == "Hans Jensen"


def test_cli_smoke(tmp_path, monkeypatch, capsys):
    import io
    import cw
    from nyms.tools import _dispatch_funcs

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    src = tmp_path / "in.txt"
    src.write_text("Hans Jensen, tlf. 12 34 56 78", "utf-8")
    out = io.StringIO()
    assert cw.dispatch(_dispatch_funcs, ["pseudonymise", str(src), "--project", "t1", "--out", str(tmp_path / "o.txt")], out=out) == 0
    assert (tmp_path / "o.txt").read_text("utf-8") == "[PERSON_1], tlf. [PHONE_1]"
    out = io.StringIO()
    assert cw.dispatch(_dispatch_funcs, ["reidentify", str(tmp_path / "o.txt"), "--project", "t1"], out=out) == 0
    assert "Hans Jensen" in out.getvalue()
    out = io.StringIO()
    assert cw.dispatch(_dispatch_funcs, ["check", "Hans Jensen igen", "--project", "t1"], out=out) == 0
    assert "Hans Jensen" in out.getvalue()
    out = io.StringIO()
    assert cw.dispatch(_dispatch_funcs, ["readable", "010190-1234", "--project", "t1"], out=out) == 0
    assert re.fullmatch(r"[a-z]+-[a-z]+\n", out.getvalue())
