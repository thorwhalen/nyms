# ADR 0002: sensitivity policy and entity taxonomy

*2026-11-08 · status: accepted · research: [terminology-and-regulation](../research/terminology-and-regulation.md) §3 and §5*

## Context

The user asked to choose what counts as sensitive, "before a sensitivity detection process, or even after one, once a list of items has been extracted", and for amounts and other non-identifying sensitive values to be in scope. Existing tools pick entities before detection (Presidio's `entities=` argument) and threshold scores after; Google DLP attaches a sensitivity level to each type; HIPAA's 18 classes and GDPR Art. 9 define legal sensitivity. No tool has Danish entity types.

## Decision

**Taxonomy** (`nyms.taxonomy.ENTITY_TYPES`): a small registry with three axes per type: identifier class (credential, direct, quasi, sensitive, organisation), tier (0 block, 1 replace by default, 2 policy decides) and aliases to Presidio, DLP and HIPAA names. Fifteen types in v1: CREDENTIAL, PERSON, CPR, EMAIL, PHONE, ADDRESS, IBAN, BANK_ACCOUNT, CASE_ID (tiers 0 and 1); CVR, ORG, AMOUNT, DATE, POSTCODE_CITY, URL (tier 2). The registry is a dict so a caller adds a type by assignment.

**Policy** (`nyms.policy.Policy`): a dataclass evaluated **after** detection: `include`/`exclude` types, `min_score` (global and per type), `allow` (never replace) and `deny` (always replace) lists on span text, and a `keep` hook. All detectors run; the policy decides; the run report lists what was detected and kept. The same object also filters detectors **before** detection (`detector_filter`, `prefilter=True` on the facade) for callers who want to skip work. Presets: `default` (tiers 0 and 1 plus CVR, ORG, AMOUNT), `identifiers` (tiers 0 and 1), `strict` (everything detected, no threshold). `with_names(...)` adds the parties to the deny list. Policies serialise to and from dicts.

**Order of operations in a run**: every detector's spans, overlap resolution (ADR 0003), the policy's split into replaced and kept, then a second pass with the project's known values (ADR 0003). Tier 0 (credentials) is replaced whatever `include` says unless excluded explicitly.

## Alternatives considered

- Policy before detection only: cheaper, but the report could not say what was seen and kept. Rejected as the only mode; offered as `prefilter`.
- Per-rule action lists (replace, mask, redact, generalise) as in the research's proposed object: deferred. v1 has two actions, replace and keep. Masking and date generalisation are additions at this seam.
- Art. 9 as a boolean flag per type: deferred with the above; the identifier class carries "sensitive" for now.

## Consequences

Dates, postcodes and URLs stay in the text by default and appear in `report["kept"]`, so a user who needs them replaced sees them and switches to `strict` or adds the type. Amounts are replaced by default because the first use case is a legal and financial dispute; `identifiers` keeps them.
