# ADR 0004: surrogate generation: typed counters by default, keyed readable words as the tool

*2026-11-08 · status: accepted · research: [surrogates-crypto-and-keys](../research/surrogates-crypto-and-keys.md), [pipeline-architecture-and-agent-practice](../research/pipeline-architecture-and-agent-practice.md) §2*

## Context

The user listed the strategies to support: aliases chosen by hand, plain numbering, a cryptographic hash, and "a cryptographic hash mapped to a sequence of letters that is actually readable", asking for the last one to be built. Two research reports disagreed on the default. The surrogate report reasoned that word-shaped tokens survive LLM paraphrase best; the pipeline report found one measured benchmark (bilingual, single vendor, 2026) in which plain bracketed typed tokens such as `[PERSON_1]` were altered least by models (1 in 8,099 occurrences, against 101 in 5,099 for XML-style tags) and restored at 99.99% with a tolerant restorer. Readable surrogates were not measured. Unkeyed hashes of low-entropy identifiers (a CPR number has at most about 10^10 values) are reversible by enumeration and are rejected by the EDPB's guidance.

## Decision

- A **strategy** is a callable `(entity_type, value, *, vault) -> str`, called once per new value by the mapping store; `vault` exposes `__contains__` and `count(entity_type)`.
- **Default: `Counter`**, `[PERSON_1]`, numbered per type within the project, persisted with the store so the numbering continues across documents. Measured evidence beats reasoning; the counter carries no information about the value.
- **`KeyedWords`**: HMAC-SHA-256 of `entity_type || NUL || value` under the project key, rendered as words. The same key gives the same surrogate on any machine without sharing a store. The key must be secret and at least 16 bytes; there is no unkeyed option. Collisions with an existing surrogate add a word.
- **`RandomWords`**: the classic tokenisation vault, random bytes rendered as words.
- **`Aliases`**: the user's own surrogates for chosen values, any other strategy as the fallback.
- **Rendering is separate from the source of bits**: `words_from_bytes(data, n, wordlist)` writes the integer in base `len(wordlist)`, most significant word first. The bundled list is the EFF short wordlist 2.0 (1,296 common words, unique three-letter prefixes, CC BY 3.0, attributed in `nyms/data/wordlists/NOTICE.md`): 10.3 bits per word, two words for about 1.7 million values. `syllables_from_bytes` is the list-free fallback. The `readable()` function and the `nyms readable` command expose the renderer stand-alone.
- **Shape**: word surrogates use a template per entity type, `Alder Brook` (name-shaped) for PERSON and ORG, `[CPR:alder-brook]` for everything else. Numbers never get checksum-valid fake numbers: a surrogate that could pass for a real identifier is a lie the reader cannot detect.
- **Re-identification is tolerant**: brackets optional, separators loose, case ignored, a genitive after the closing bracket allowed, longest surrogate first, and a word boundary required when the bracket is missing so `PERSON_1` never matches inside `PERSON_11`. Tokens that look like ours but were never issued are reported as `unmatched`, never guessed.

## Alternatives considered

- Format-preserving encryption (FF1): a replacement for numeric identifiers only; NIST's 2025 draft keeps FF1 alone and the maintained Python library implements the withdrawn FF3 variants. Not built.
- Seeded Faker names: realistic, but a fake that matches a real person is a risk and the dependency is large. A replacement at this seam.
- XML-style tags: measured worse. Rejected.

## Consequences

Text sent to a model reads as `[PERSON_1] owes [AMOUNT_1]`, which is less fluent than a readable name but round-trips best. A user who wants fluent text switches to `KeyedWords` with one argument and accepts an unmeasured round-trip risk, which `check()` and the `unmatched` list make visible.
