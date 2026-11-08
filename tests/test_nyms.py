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


def test_word_surrogates_round_trip_exact_case_only():
    p = Pseudonymiser(store={}, strategy=KeyedWords(b"k" * 32))
    r = p.pseudonymise("Rasmus Jensen (CPR 010190-1234) ringede.")
    back = p.reidentify(r.text)
    assert "Rasmus Jensen" in back.text and "010190-1234" in back.text
    # A name-shaped surrogate is matched exactly (case included) so ordinary prose is left alone;
    # a bracketed one stays tolerant.
    lowered = p.reidentify(r.text.lower())
    assert "Rasmus Jensen" not in lowered.text and "010190-1234" in lowered.text
    person_surrogate = next(sur for span, sur in r.replacements if span.entity_type == "PERSON")
    assert p.reidentify(f"the {person_surrogate.lower()} is a creek").text == f"the {person_surrogate.lower()} is a creek"


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
    assert cw.dispatch(_dispatch_funcs, convention=cw.Convention(naming=cw.BY_NAME_IF_KWONLY), argv=["pseudonymise", "--path", str(src), "--project", "t1", "--out", str(tmp_path / "o.txt")], out=out) == 0
    assert (tmp_path / "o.txt").read_text("utf-8") == "[PERSON_1], tlf. [PHONE_1]"
    out = io.StringIO()
    assert cw.dispatch(_dispatch_funcs, convention=cw.Convention(naming=cw.BY_NAME_IF_KWONLY), argv=["reidentify", "--path", str(tmp_path / "o.txt"), "--project", "t1"], out=out) == 0
    assert "Hans Jensen" in out.getvalue()
    out = io.StringIO()
    assert cw.dispatch(_dispatch_funcs, convention=cw.Convention(naming=cw.BY_NAME_IF_KWONLY), argv=["check", "Hans Jensen igen", "--project", "t1"], out=out) == 0
    assert "Hans Jensen" in out.getvalue()
    out = io.StringIO()
    assert cw.dispatch(_dispatch_funcs, convention=cw.Convention(naming=cw.BY_NAME_IF_KWONLY), argv=["readable", "010190-1234", "--project", "t1"], out=out) == 0
    assert re.fullmatch(r"[a-z]+-[a-z]+\n", out.getvalue())


# --------------------------------------------------------------------------- review regressions


def test_identifier_inside_a_kept_url_is_still_replaced():
    p = Pseudonymiser(store={})
    r = p.pseudonymise("Link: https://x.dk/cpr/010190-1234 og https://x.dk/?mail=rasmus.jensen@example.dk")
    assert "010190-1234" not in r.text and "rasmus.jensen@example.dk" not in r.text
    assert any(k.entity_type == "URL" for k in r.kept)


def test_all_caps_names_are_whole():
    p = Pseudonymiser(store={})
    r = p.pseudonymise("SAGSØGTE: METTE HOLM. Senere skrev Mette Holm igen.")
    assert r.text == "SAGSØGTE: [PERSON_1]. Senere skrev [PERSON_1] igen."


def test_surname_ending_in_s_is_not_mutilated():
    p = Pseudonymiser(store={})
    r = p.pseudonymise("Niels Thomas kom.")
    assert r.text == "[PERSON_1] kom." and p.mapping.original("[PERSON_1]") == "Niels Thomas"


def test_genitive_seen_first_relinks_to_base_form():
    p = Pseudonymiser(store={})
    a = p.pseudonymise("Rasmus Jensens bil.")
    b = p.pseudonymise("Rasmus Jensen kom.")
    assert a.text == "[PERSON_1] bil." and b.text == "[PERSON_1] kom."
    assert p.mapping.original("[PERSON_1]") == "Rasmus Jensen"


def test_unicode_nfd_and_non_danish_letters():
    import unicodedata

    p = Pseudonymiser(store={})
    nfd = unicodedata.normalize("NFD", "Søren Østergård Jensen bor på Nørrebrogade 12, 2200 København N.")
    r = p.pseudonymise(nfd)
    assert r.text == "[PERSON_1] bor på [ADDRESS_1]."
    r2 = Pseudonymiser(store={}).pseudonymise("Her mødtes Łukasz Nowak og Ayşe Çelik og José Núñez.")
    assert r2.text == "Her mødtes [PERSON_1] og [PERSON_2] og [PERSON_3]."


def test_scaled_amounts():
    p = Pseudonymiser(store={})
    r = p.pseudonymise("Kravet er 1,2 mio. kr. og 2 mio. kr. i alt, samt kr. 1.200,50.")
    assert r.text == "Kravet er [AMOUNT_1] og [AMOUNT_2] i alt, samt [AMOUNT_3]."


def test_report_attributes_spans_to_the_detector_that_found_them():
    p = Pseudonymiser(store={})
    r = p.pseudonymise("Rasmus Jensen, CPR 010190-1234, 12 34 56 78, Vesterbro Ejendomme ApS")
    by = r.report["replaced_by_detector"]
    assert "known_values" not in by and by["cpr"] == 1 and by["dk_phone"] == 1 and by["org_name"] == 1
    assert "known_values" in r.report["detectors_run"]


def test_name_components_resolve_to_the_known_person():
    p = Pseudonymiser(store={}, names=["Rasmus Jensen"])
    r = p.pseudonymise("Rasmus Jensen kom. Rasmus gik. Jensen blev. Jensens bil.")
    assert r.text == "[PERSON_1] kom. [PERSON_1] gik. [PERSON_1] blev. [PERSON_1]s bil."
    r2 = Pseudonymiser(store={}).pseudonymise("Anne-Marie Nielsen og H.C. Andersen mødtes.")
    assert r2.text == "[PERSON_1] og [PERSON_2] mødtes."


def test_surrogate_canon_collision_is_rejected_and_output_is_idempotent():
    strategy = Aliases({"Mette Holm": "Person 1"}, fallback=Counter())
    p = Pseudonymiser(store={}, strategy=strategy, names=["Mette Holm", "Hans Jensen"])
    p.pseudonymise("Hans Jensen kom.")
    with pytest.raises(ValueError):
        p.pseudonymise("Mette Holm kom.")
    q = Pseudonymiser(store={}, strategy=KeyedWords(b"k" * 32))
    once = q.pseudonymise("Hans Jensen mødte Mette Holm.")
    twice = q.pseudonymise(once.text)
    assert twice.text == once.text and len(q.mapping) == 2


def test_two_instances_on_one_store_stay_consistent(tmp_path):
    store = lambda: local_mapping_store("q", rootdir=tmp_path)  # noqa: E731
    a = Pseudonymiser("q", store=store(), key=b"k" * 32)
    b = Pseudonymiser("q", store=store(), key=b"k" * 32)
    a.pseudonymise("Hans Jensen")
    assert b.pseudonymise("Hans Jensen og Mette Holm").text == "[PERSON_1] og [PERSON_2]"


def test_codec_mismatch_is_a_clear_error(tmp_path):
    pytest.importorskip("cryptography")
    from nyms.mapping import StoreError

    local_mapping_store("enc", rootdir=tmp_path, codec=encrypted(b"k" * 32))
    with pytest.raises(StoreError):
        local_mapping_store("enc", rootdir=tmp_path)


def test_bare_eight_digit_number_needs_context_to_be_a_cvr():
    p = Pseudonymiser(store={})
    assert p.pseudonymise("Faktura nr. 10150817 betalt.").text == "Faktura nr. 10150817 betalt."
    assert p.pseudonymise("CVR 10150817 betalt.").text == "CVR [CVR_1] betalt."


def test_labelled_case_id_keeps_label_and_month_abbreviation_is_not_a_name():
    p = Pseudonymiser(store={})
    assert p.pseudonymise("sagsnr. ABC-1234. Den 1. jan. 2024.").text == "sagsnr. [CASE_ID_1]. Den 1. jan. 2024."


def test_reidentify_keeps_whitespace_and_handles_unbracketed_tokens():
    p = Pseudonymiser(store={})
    p.mapping.add("PERSON", "Hans Jensen")
    assert p.reidentify("Hej, PERSON_1 og (PERSON_1)").text == "Hej, Hans Jensen og (Hans Jensen)"


def test_project_names_are_file_system_safe():
    from nyms.keys import _check_project_name

    for bad in (".hidden", "a:b", "a/b", "", "a b"):
        with pytest.raises(ValueError):
            _check_project_name(bad)


def test_allow_list_does_not_exempt_credentials():
    pol = Policy.default()
    pol.allow = frozenset({"sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"})
    r = Pseudonymiser(store={}, policy=pol).pseudonymise("key sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789")
    assert "sk-ant" not in r.text


def test_post_detectors_seam_runs_on_pseudonymised_text():
    from nyms import Span

    def fake_model_pass(text):
        # a "model" that spots an unlisted name the deterministic pass missed, and (wrongly)
        # also flags an existing surrogate, which must be protected
        for word in ("Zorblax", "[PERSON_1]"):
            i = text.find(word)
            if i >= 0:
                yield Span(i, i + len(word), "PERSON", word, 0.9, "fake_model")

    p = Pseudonymiser(store={}, post_detectors=[fake_model_pass])
    r = p.pseudonymise("Hans Jensen mødte Zorblax.")
    assert r.text == "[PERSON_1] mødte [PERSON_2]."
    assert r.report["replaced_by_detector"] == {"first_names": 1, "fake_model": 1}
    assert p.reidentify(r.text).text == "Hans Jensen mødte Zorblax."


def test_tools_do_not_guess_paths(tmp_path):
    from nyms import tools

    f = tmp_path / "secret.txt"
    f.write_text("Hans Jensen", "utf-8")
    spans = tools.detect(str(f))
    assert all(s["text"] != "Hans Jensen" for s in spans)
    assert tools.detect(path=str(f))[0]["text"] == "Hans Jensen"
    with pytest.raises(ValueError):
        tools.detect("x", path=str(f))
