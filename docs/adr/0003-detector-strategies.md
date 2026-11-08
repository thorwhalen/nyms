# ADR 0003: detector strategies: a deterministic pass first, a model pass as a seam

*2026-11-08 · status: accepted · research: [detection-libraries-and-methods](../research/detection-libraries-and-methods.md), [pipeline-architecture-and-agent-practice](../research/pipeline-architecture-and-agent-practice.md)*

## Context

The user's requirement: a non-AI pass runs before any content reaches a model, with an optional heavier model-based pass afterwards. The research found no library with Danish recognisers (Presidio has none; Google DLP has only the CPR type), that the CPR modulus-11 check is unreliable for numbers issued since October 2007, that recall is the metric de-identification systems optimise, and that the best Danish NER options (spaCy `da_core_news`, DaCy, GLiNER PII checkpoints) are heavy, optional dependencies.

## Decision

- **Native deterministic detectors** (`nyms.detect`): a `Detector` is a compiled regex plus an optional validator (checksum, calendar, stop list) plus context words that raise the score. v1 ships: CPR (date check required, mod-11 only raises the score), CVR (mod-11 plus context), DK VAT, e-mail, Danish and international phone, IBAN (mod-97 required), Danish bank account, Danish and English addresses, Danish postcode and town, amounts (prefix or suffix currency, Danish thousand separators), dates (numeric, Danish and English textual), case and journal numbers, URLs, credentials (vendor prefixes and one assignment heuristic, after `openloops.egress`), organisation names by legal-form suffix, titled names, a capitalised-sequence name heuristic at a low score, a bundled first-name gazetteer (Danish and English) and the caller's known names.
- **Overlap resolution** (`nyms.spans.resolve_overlaps`): strong spans (score at or above 0.6) outrank weak ones whatever their length; among equals the longer, then the higher score, then the earlier. A function, so it is testable and replaceable.
- **Two passes for consistency**: after the first pass enters new values into the mapping, a second pass adds a detector per entity type for every value the project already knows, so an occurrence scored too low (a name at a sentence start, a company in a heading) is replaced once the value was accepted anywhere, in this document or an earlier one. This is the benchmark engine's "propagate to every mention" behaviour.
- **Genitive handling**: detectors never strip anything (a surname may end in `s`: "Niels Thomas"). The mapping store maps `<known value>s` to the known value's surrogate plus the suffix, and the facade writes `[PERSON_1]s`; a genitive seen before its base form is taken literally and relinked when the base form appears.
- **Nested promotion**: an accepted span inside a span the policy keeps (a CPR number inside a URL) is still replaced; the kept span stays in the report.
- **Name components**: a surname or first name that identifies exactly one known person (from `names=` or the mapping) stands for that person at score 0.8, so "Jensen blev" becomes `[PERSON_1] blev`. Capitalised words include all-capitals headings (`METTE HOLM`), hyphenated names and initials (`H.C. Andersen`). Letters are the Latin letters of Unicode's blocks up to Latin Extended-B, and text is NFC-normalised first.
- **Surrogate protection**: the project's own surrogates are detected as a pseudo-type that wins overlap resolution and is never acted on, so pseudonymising already pseudonymised text is idempotent.
- **Model-based second pass**: the `post_detectors` seam (added after the adversarial review showed a plain detector could not do it, since it runs on different text). Any callable `text -> Iterable[Span]`; it runs on the already-pseudonymised text, so the model never sees what the first pass caught, with the surrogates protected from re-detection; what it finds is replaced in that text and added to the mapping, and the report lists it under its own name. Default: none. Candidates: DaCy or spaCy Danish models, GLiNER PII (Apache-2.0), an LLM through `aix` or `creel`. Piiranha and the ai4privacy data are excluded by licence.
- **Recall over precision**, with the policy threshold as the user's dial; the heuristic exists because a missed name leaks and a redundant replacement only costs readability.

## Consequences

False positives occur (a capitalised phrase replaced as a person); they are visible in the report and reversible. A bare eight-digit number is ambiguous between phone and CVR and is decided by checksum and context. OCR noise and inflected compounds are not handled in v1 (documented limits).

## Fixtures

Synthetic Danish and English documents under `tests/fixtures/`, with `expected.json` naming what must be replaced and what must be detected but kept; a leakage test (no original, nor its digit string, survives) and a round-trip test per fixture. No real data; the CPR and CVR numbers are checksum-valid synthetic values or deliberately invalid ones.
