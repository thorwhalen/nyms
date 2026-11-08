# ADR 0001: nyms does pseudonymisation, and says so

*2026-11-08 · status: accepted · research: [terminology-and-regulation](../research/terminology-and-regulation.md), [synthesis](../research/deidentification-synthesis.md)*

## Context

The package replaces personal and sensitive identifiers in text before the text reaches an AI service, and can put them back. The user's words for this were "redaction", "mapping to keys", "anonymising". The established vocabulary differs, and the difference carries legal weight: under GDPR Art. 4(5) data that can be re-attributed with separately held additional information is **pseudonymised** and remains personal data (Recital 26); only data that no reasonably likely means can re-attribute is anonymous. The EDPB's 2025 guidelines on pseudonymisation use the same terms and name the mapping and keys the **additional information**, kept outside the **pseudonymisation domain** [1].

## Decision

- The package, its API and its documentation say **pseudonymise** / **re-identify**, never "anonymise". The report of every run ends with a fixed caveat sentence (`nyms.core.CAVEAT`) saying so.
- Vocabulary, used consistently: **detector** (finds spans), **span** (character interval with entity type and score), **policy** (which spans are acted on), **surrogate** (the replacement; a *pseudonym* when it names a person), **surrogate strategy** (how surrogates are generated), **mapping store** (surrogate to original, per **project**), **key** (the project's secret), **re-identification** (restoring originals), **leak check** (originals found in outgoing text).
- British spelling throughout (`pseudonymise`), matching the EU sources that define the terms.
- What nyms claims: identifiers it detected were replaced before the text left the machine, and the mapping stayed local. What it never claims: that the output is anonymous, or a numeric risk score. Residual risk is reported as coverage (what was detected, replaced, kept, and which detectors ran), not as a probability.

## The seams (architecture-first, turn 1)

| # | Seam | v1 default (no new dependency) | Replacement it allows |
|---|---|---|---|
| 1 | `detectors` | regex, checksum and gazetteer detectors (`nyms.detect.default_detectors`) | a model-based second pass (spaCy/DaCy, GLiNER, an LLM through `aix` or `creel`), a Presidio adapter |
| 2 | `policy` | `Policy.default()` (tiers 0 and 1, plus CVR, ORG, AMOUNT) | `strict()`, `identifiers()`, a serialised policy file |
| 3 | `strategy` | `Counter` (`[PERSON_1]`) | `KeyedWords`, `RandomWords`, `Aliases`, format-preserving encryption |
| 4 | `store` | `dol.JsonFiles` under `~/.local/share/nyms/<project>/mapping` | any `MutableMapping`; `encrypt=True` for Fernet at rest; SQLite, S3 through `dol` |
| 5 | `key` | `resolve_key`: env var, then a 0600 key file, then a passphrase | `keyring`, `config2py`, `age`, a KMS |

Surface for v1: Python facade, shipped agent skill, CLI (`cw`). MCP and HTTP: the tools module is the SSOT they would wrap; not built. NOT seams: the span data model, the report shape, the tolerant re-identification matcher, the overlap rule's signature.

## Consequences

Users and agents read "pseudonymised" and know the mapping is a key. The client-facing risk guide (a separate document in another repository) owns the legal framing and the advice on what not to send; nyms owns the numbers a run can compute.

## REFERENCES

1. [EDPB, Guidelines 01/2025 on Pseudonymisation](https://www.edpb.europa.eu/system/files/2025-01/edpb_guidelines_202501_pseudonymisation_en.pdf)
