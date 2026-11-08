---
name: nyms-dev-deidentification
description: The expert index for working on de-identification and reversible pseudonymisation in the nyms package, for agents developing or extending it. Routes to the research reports (terminology and regulation, detection libraries and methods, surrogates and key management, pipeline architecture), the five ADRs, the seam table, the test rules (leakage, round trip, consistency) and the vocabulary to use. Use when adding a detector or entity type, a surrogate strategy, a store backend, the model-based second pass, Danish or English fixtures, or when a question about pseudonymisation, PII detection, CPR/CVR validation, keyed hashing, format-preserving encryption, re-identification risk or key management comes up while developing nyms.
metadata:
  audience: developers
---

# nyms-dev-deidentification: the map for working on nyms

Use the field's words, not the user's: pseudonymisation (never anonymisation), surrogate, strategy, mapping store, additional information, pseudonymisation domain, re-identification, leak check, detector, span, policy, tier. ADR 0001 defines them; `references/vocabulary.md` is the short list with the user's phrasings they replace.

## Read first, by question

| Question | Read |
|---|---|
| What may nyms claim, legally and in its README? | `docs/adr/0001-pseudonymisation-not-anonymisation.md`, `docs/research/terminology-and-regulation.md` §1–§2 |
| Which entity types exist, what tier, how does the policy decide? | `docs/adr/0002-sensitivity-policy-and-entity-taxonomy.md`, `nyms/taxonomy.py`, `nyms/policy.py` |
| How do detectors work, why is CPR mod-11 not a gate, how are overlaps resolved, why two passes? | `docs/adr/0003-detector-strategies.md`, `docs/research/detection-libraries-and-methods.md`, `nyms/detect.py`, `nyms/spans.py` |
| Which surrogate form, why `[PERSON_1]` by default, how do keyed words work, how tolerant is re-identification? | `docs/adr/0004-surrogate-generation.md`, `docs/research/surrogates-crypto-and-keys.md`, `docs/research/pipeline-architecture-and-agent-practice.md` §2, `nyms/surrogates.py`, `nyms/core.py` |
| Where do the mapping and key live, encryption, rotation, loss? | `docs/adr/0005-mapping-store-and-key-management.md`, `nyms/mapping.py`, `nyms/keys.py` |
| What did the research conclude overall, and what is still open? | `docs/research/deidentification-synthesis.md` |
| Which libraries were assessed and with what verdict? | `docs/research/detection-libraries-and-methods.md` §1 (Presidio, scrubadub, spaCy/DaCy, GLiNER, Piiranha, gitleaks, detect-secrets) |

## The seams (one keyword argument each; add at them, do not add new ones without an ADR)

`Pseudonymiser(project, *, detectors, policy, strategy, store, key)`. The table with defaults and allowed replacements is in ADR 0001. The SSOT of operations is `nyms/tools.py`; the CLI (`nyms/__main__.py`, `cw`) dispatches it, and an MCP or HTTP surface would reference the same functions.

## Adding things

- **A detector**: a `Detector(name, entity_type, pattern, score, validate, group, context)` in `nyms/detect.py`, appended in `default_detectors`. Register a new entity type in `nyms/taxonomy.py` with class and tier first. Scores: 1.0 certain (checksum or gazetteer), 0.9 strong pattern, 0.6–0.8 pattern with ambiguity, below 0.6 heuristic (a weak span never outranks a strong one in overlap resolution). Add the value to a fixture and to `tests/fixtures/expected.json`.
- **A surrogate strategy**: a callable `(entity_type, value, *, vault) -> str` in `nyms/surrogates.py`; must be deterministic or vault-checked, never an unkeyed hash of the value.
- **The model-based second pass**: a detector callable run on the already-pseudonymised text, spans mapped back through the replacement offsets, spans inside existing surrogates dropped. Candidates and their licences: detection report §1; design: ADR 0003.
- **A store backend**: any `MutableMapping[str, dict]`; see `local_mapping_store` for the `dol` idiom and the `codec` seam.

## Test rules (never relax them)

1. **Leakage**: for every fixture and every `must_replace` value, neither the value nor its digit string appears in the output.
2. **Round trip**: `reidentify(pseudonymise(x).text)` restores every replaced span, `unmatched` is empty, `check` on the output is empty.
3. **Consistency**: the same value gets the same surrogate across documents of a project, including the Danish genitive; two people with one surname get two surrogates.
4. **Prefix safety**: `[PERSON_1]` never matches inside `[PERSON_11]`.
5. Fixtures are synthetic. No real person, no client material, ever, in this public repository.

## Open work (file issues here, not notes)

The synthesis lists the open questions: a Danish round-trip benchmark of surrogate forms, the Danish NER choice for the second pass, the final EDPB 01/2025 text, a redistributable Danish name list, quasi-identifier actions (date shifting, amount bucketing).
