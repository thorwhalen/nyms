# De-identification toolkit research synthesis: what nyms uses and why

*2026-11-08 · scope: the four theme reports in this folder · requested for: the design of `nyms`, a reversible pseudonymisation toolkit for Danish and English text sent to AI services*

## Summary and recommendation

- **Name the thing correctly**: pseudonymisation (GDPR Art. 4(5)), with the mapping and key as the "additional information" kept outside the pseudonymisation domain. Never claim anonymity; report coverage, not a risk score. The EDPB's 2025 guidelines and the CJEU's 2025 *EDPS v SRB* judgment are the framing; the final post-consultation EDPB text was not confirmed [1][2].
- **Write the deterministic detectors natively.** No library has Danish recognisers; Presidio, the most mature, has none, and Google DLP has only the CPR type [3][4]. The CPR modulus-11 check cannot be a gate (numbers issued since October 2007 need not pass it) [5]. Study Presidio's span contract, context scoring and overlap rules; do not depend on it.
- **Default surrogate: `[PERSON_1]`-style bracketed typed counters**, per project, because the only measured benchmark found them altered least by LLMs and restored at 99.99% with a tolerant restorer [6]. Readable keyed-word surrogates are the opt-in strategy and the stand-alone tool the user asked for; the EFF short wordlist (CC BY 3.0) renders them [7]. Unkeyed hashes are rejected [1].
- **The store is the product's state**: a per-project `dol` store with the key held separately, encryption at rest as an optional codec, propagation of known values to every mention, and a tolerant, non-guessing re-identifier that reports invented tokens. Presidio's statelessness is the gap every LLM gateway had to fill [8][9].
- **Agent surface**: four verbs (`pseudonymise`, `reidentify`, `check`, `detect`) over one facade, a shipped skill that makes the deterministic pass the first step before any content reaches a model, and a leak check that blocks rather than warns.

## Where the reports agree

All four put a detect / transform / reverse split at the centre, with character-offset spans and a score, and all treat the mapping as sensitive. All say recall beats precision for this task and that the residual risk must be stated in words, not a number. All find Danish support absent from existing tools.

## Where they disagree, and the resolution

| Question | Surrogates report | Pipeline report | Resolution in nyms |
|---|---|---|---|
| Default surrogate form | random readable word tokens, name-shaped | bracketed typed token `[PERSON_1]` | **Counter default** (measured), `KeyedWords`/`RandomWords` opt-in (ADR 0004) |
| Default key store | OS keyring | `config2py` | **key file under the config dir**, env var override, passphrase option; keyring and config2py as replacements (ADR 0005) |
| Encryption at rest | required default | encrypted file | **optional codec** (no stdlib cipher; a default must not need a new dependency); README states the trade-off (ADR 0005) |

## What the build uses

| Part | From the research | Implementation |
|---|---|---|
| Vocabulary and caveat | terminology report §1, §2 | ADR 0001, `nyms.core.CAVEAT` |
| Taxonomy and policy | terminology report §3, §5 | ADR 0002, `nyms.taxonomy`, `nyms.policy` |
| Detectors, overlap rule, two passes | detection report §1–§3, pipeline report §2 | ADR 0003, `nyms.detect`, `nyms.spans` |
| Strategies, word rendering, tolerant restorer | surrogates report §1–§2, pipeline report §2 | ADR 0004, `nyms.surrogates`, `nyms.core.reidentify` |
| Store, key, rotation, loss | surrogates report §3–§4 | ADR 0005, `nyms.mapping`, `nyms.keys` |
| Fixtures and tests | detection report §4, pipeline report §5 | `tests/fixtures/`, leakage and round-trip tests; Faker's `da_DK` has no CPR generator, so fixtures carry hand-made values |

## In-house components reused

`dol` (the store facade), `cw` (the CLI from the tools module), the pattern design of `openloops.egress` (credential prefixes, one heuristic rule last). Found but not used in v1: `hm` (Major System; a rendering aid, not a hash encoding), `creel` and `aix` (candidates for the model-based second pass), `config2py` (a key-resolution replacement).

## Open questions carried forward

1. Does the bracketed-token advantage hold for Danish and for current frontier models? Rerun the benchmark method on the Danish fixtures (an issue).
2. Which Danish NER (DaCy, spaCy, GLiNER PII) is good enough for the second pass, measured by leakage rate on the fixtures?
3. Is the final EDPB 01/2025 text changed on hashing and key separation?
4. A Danish name list with a redistributable licence: Danmarks Statistik's terms were not found.
5. Quasi-identifier actions (date shifting, amount bucketing) and Art. 9 flags: deferred from the policy (ADR 0002).

## REFERENCES

1. [EDPB, Guidelines 01/2025 on Pseudonymisation](https://www.edpb.europa.eu/system/files/2025-01/edpb_guidelines_202501_pseudonymisation_en.pdf)
2. [EUR-Lex, Case C-413/23 P, EDPS v SRB](https://eur-lex.europa.eu/eli/C/2025/5551/oj/eng)
3. [Presidio, supported entities](https://presidio.dataprivacystack.org/supported_entities/)
4. [Google Sensitive Data Protection, infoType reference](https://docs.cloud.google.com/sensitive-data-protection/docs/infotypes-reference)
5. [LookupTax, Denmark TIN: CPR and CVR number guide](https://www.lookuptax.com/docs/tax-identification-number/denmark-tax-id-guide)
6. [Beskorovainyi V. Reversible Pseudonymisation of Documents Sent to External LLMs, arXiv:2610.34012 (2026)](https://arxiv.org/html/2610.34012)
7. [EFF, Deep Dive: EFF's New Wordlists for Random Passphrases](https://www.eff.org/dice)
8. [Presidio Anonymizer documentation](https://presidio.dataprivacystack.org/anonymizer/)
9. [LLM Guard Anonymize scanner](https://protectai.github.io/llm-guard/input_scanners/anonymize)

The theme reports: [terminology-and-regulation](terminology-and-regulation.md), [detection-libraries-and-methods](detection-libraries-and-methods.md), [surrogates-crypto-and-keys](surrogates-crypto-and-keys.md), [pipeline-architecture-and-agent-practice](pipeline-architecture-and-agent-practice.md). Prompts used: [prompts/](prompts/).
