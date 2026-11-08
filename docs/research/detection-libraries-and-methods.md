# Detection libraries and methods for nyms

*2026-11-08. Scope: existing PII detection libraries, models and methods for the detector-strategy seam of `nyms` (deterministic pass first, optional model pass second), Danish and English text. Serves the choice of what to depend on, wrap, study or avoid.*

## Summary and recommendation

No surveyed library covers Danish identifiers. Presidio, the most mature framework, has no Danish recogniser: its country-specific list includes Sweden, Finland and Germany but not Denmark [1]. So the CPR (personal identity number), CVR (company number), Danish phone, address and IBAN recognisers have to be written in `nyms`, whatever else is adopted.

- Write the deterministic pass natively: regex, checksum and context rules, behind a small `Detector` protocol returning spans. Do not make Presidio a hard dependency (it pulls in spaCy and a model download). Study its design (recogniser, score, context enhancement, overlap resolution) and optionally offer an adapter extra that runs a Presidio `AnalyzerEngine` and converts its results to spans.
- The CPR modulus-11 check must not be a gate. Since 1 October 2007 the CPR office issues numbers that need not pass it [2][3]. Use it only to raise confidence; detect on format plus a valid birth date plus context words.
- For the optional model pass, the best licence-clean candidates are GLiNER (generalist named-entity model driven by free-text labels) PII checkpoints under Apache-2.0 [4][5], plus spaCy `da_core_news_*` or DaCy for Danish names, places and organisations [6][7]. Piiranha is CC BY-NC-ND and the ai4privacy data is non-commercial, so both are unusable in an MIT package [8][9].
- Treat recall as the primary metric and measure leakage rate (share of true identifiers surviving in the output) next to span F1. Published de-identification systems choose recall over precision for the same reason [10].
- Faker's `da_DK` locale does not generate CPR numbers: the Danish SSN provider is misfiled as `dk_DK` and only produces VAT ids, so `da_DK` falls back to US-format SSNs (checked, below). Fixtures need an own CPR generator.

## 1. Libraries and tools

Verdicts are for `nyms` as an MIT library with a deterministic default and no mandatory heavy dependency.

| Tool | Maturity, licence | Danish / English | Weight | Verdict |
|---|---|---|---|---|
| Microsoft Presidio (analyzer, anonymizer) | MIT, about 11.8k stars, actively developed [1][11] | Many country recognisers, none Danish; non-English needs a configured NLP engine per language and per-language recognisers [12] | Heavy (spaCy plus models) | Study, optional adapter extra. Do not depend on it in core |
| scrubadub | Apache-2.0, maintained by LeapBeyond; add-ons for spaCy and Stanford NER [13] | US/GB oriented detectors; locale mechanism exists | Light core | Study (its `Filth` and detector/post-processor split); avoid as dependency |
| Philter (UCSF) | Open source clinical-text filter; licence not verified by me; reported recall 99.46% on its own UCSF corpus [14] | English clinical | Light, rule based | Study: a pure rule-and-dictionary design that achieved high recall |
| pii-codex, anonympy | Not examined in depth; could not verify maturity or licence in this pass | n/a | n/a | Not assessed |
| Google Cloud DLP, AWS Comprehend | Proprietary APIs | Broad infoTypes, weak Danish-specific | Network, data leaves the machine | API reference only. Sending text to them defeats the purpose |
| spaCy `da_core_news_sm/md/lg/trf` | Four Danish pipelines with NER, trained on news text [6] | Danish persons, places, organisations; weaker on legal and medical prose | 15 MB to several hundred MB, plus `trf` needs PyTorch | Optional model-pass extra |
| DaCy | Danish pipelines trained on DANSK, up to 0.82 macro F1 on 18 fine-grained categories [7] | Danish | spaCy-based | Optional model-pass extra; best Danish NER evidence |
| GLiNER (`urchade/gliner_multi_pii-v1`) | Apache-2.0; fine-tune of a multilingual GLiNER on a synthetic PII set; labels chosen at inference [4] | Card says six languages without naming them; Danish not verified | Transformer, CPU feasible | Wrap as optional detector; test on Danish fixtures first |
| GLiNER-PII (`knowledgator/gliner-pii-*`) | Apache-2.0; 60+ PII categories; F1 80.99% (base) on a synthetic benchmark; ONNX 197 to 330 MB; threshold 0.3 suggested [5] | English plus "multilingual" tag; Danish unverified | Moderate | Wrap as optional detector; synthetic-only benchmark, so expect lower real-world scores |
| Piiranha (`iiiorg/piiranha-v1-detect-personal-information`) | CC BY-NC-ND 4.0; 17 PII types; 256-token context; six languages without Danish [8] | No Danish | 0.3B parameters | Avoid: licence and language |
| Stanza, flair | Not examined in this pass | Stanza has Danish models (not verified here) | Heavy | Not assessed; spaCy/DaCy suffice |
| LLM detection | Prompted extraction with structured output | Strong on Danish | Network or local model | Second pass only, on already-pseudonymised text (section 5) |
| gitleaks | MIT; regex plus entropy plus keyword prefilter; maintainer says feature complete, security patches only [15] | Language neutral | Go binary | Study its rule format; credential patterns already exist in `openloops.egress` |
| detect-secrets | Apache-2.0; regex, entropy and keyword plugins [16] | Language neutral | Pure Python | Study; optionally reuse its plugin patterns for the credentials class |
| trufflehog, commoncrawl-style regex collections | Not examined | n/a | n/a | Not assessed |

Presidio's design is worth copying in outline: a recogniser yields entity type, span and a score; context words near a match raise the score; an overlap resolver keeps the best span [12].

## 2. Methods

- **Regex plus validation.** Validation separates real identifiers from digit strings: Luhn for payment cards, mod-97 for IBAN, a calendar check on the first six CPR digits. Modulus 11 for CPR is a weak signal only (see summary) [2][3]. CVR has its own modulus-11 weighting, which I did not verify here; check the CVR specification before relying on it.
- **Gazetteers.** Danmarks Statistik publishes name statistics (whole population from 2002, newborn names from 1985) [17]; I found no licence terms for the table data, so contact or check terms before redistributing a list inside the package; download at first use instead. The address registry route is unstable: DAWA, the address API, is being shut down in 2026 with sources disagreeing on the exact dates (address data frozen about April 2026, closure about 1 July 2026) and its replacement is the modernised Datafordeler, which uses GraphQL [18]. Do not build on DAWA.
- **Context words and scoring.** A bare ten-digit string is ambiguous; "CPR", "personnummer", "cpr-nr" nearby raises confidence. Keep scores explicit so a threshold is a seam, not a constant.
- **NER (named-entity recognition).** Needed for person, organisation and location names that no pattern captures; see the models above.
- **Span conflict resolution.** Detectors overlap (an IBAN contains digits that look like a phone number; a CPR sits inside a longer case number). Use a deterministic rule: higher priority class wins, then longer span, then higher score, then earlier start; nested spans of the same entity are merged. Make the rule a function so it is testable.

## 3. Failure modes

- **Danish inflection.** The genitive "-s" ("Hansens", "Jensens bil") and compounds ("Jensenfamilien") defeat exact-token lookups. Match the stem with an optional "-s" and, for compounds, allow a known name as prefix or suffix; this raises false positives, which is the accepted direction.
- **Case, diacritics, ASCII fallbacks.** "Søren" versus "Soren", "Århus" versus "Aarhus", all-caps headers. Normalise for matching, keep original offsets for replacement.
- **OCR noise.** Digit confusions (O/0, l/1) and broken spacing inside identifiers. Allow tolerant patterns for structured identifiers when the input is known to be OCR output.
- **Quasi-identifiers.** Dates, amounts, rare job titles and small-town names can single out a person without any direct identifier; these are a re-identification risk, not a pattern match, and need an explicit policy (generalise or leave, user choice).
- **Names that are common words.** "Bo", "Lund", "Mark", "Rose". A model with context helps; a pure list over-redacts.
- **False positives on legal citations and case numbers.** "Sag nr. 12-3456/2021", "U.2019.1234H" and statute paragraph numbers resemble identifiers; use negative context words and a per-class allow pattern.
- **Recall over precision.** A missed identifier leaks; a redundant replacement only costs readability. Philter reports 99.46% recall against 85.10% and 95.30% for two competing tools on one corpus, and was built for recall [14]; recall-optimised LLM redaction also over-masks [19].

## 4. Evaluation

| Resource | Use | Caveat |
|---|---|---|
| DaNE, DANSK [7] | Danish NER benchmark (DANSK: 18 categories, multiple domains) | Not PII-labelled; measures names, places and organisations only. Licence terms not checked |
| ai4privacy pii-masking-400k [9] | Large PII-labelled set | Academic, non-commercial licence; six languages without Danish; do not ship or derive from it |
| i2b2/n2c2 de-identification challenges | Clinical English gold standard; Philter was evaluated on the 514-note i2b2 2014 test set [14] | Data-use agreement required; cannot be redistributed |
| PII-Bench | Named in the brief | Not verified in this pass |
| Faker, Mimesis | Synthetic Danish fixtures | See below |

Faker check (version 40.44.0, installed in a scratch environment): `Faker('da_DK')` generates Danish names and addresses, but `ssn()` returned US-format values (for example `815-32-2277`). The Danish provider sits in `faker/providers/ssn/dk_DK` (not `da_DK`) and only implements `vat_id` as `DK` plus eight digits; there is no CPR generator. Plan: write a small CPR generator in the test fixtures (valid date, serial digits, with and without the modulus-11 property, matching the post-2007 reality). Mimesis was not examined.

Metrics: span-level F1 (exact boundaries) for comparability, entity-level recall per class, and a leakage rate (identifiers surviving after replacement, counted on the final text), since boundary mismatches that still remove the identifier should not count as misses for the safety goal.

## 5. Two-pass designs

I found no study that tests exactly a deterministic first pass followed by an LLM second pass over the already-pseudonymised text; the closest results are partial:

- RedactOR (clinical) runs LLM passes in which already-found entities are masked and the model is re-prompted for those it missed; gains are largest between the first and second pass and taper afterwards [19].
- A dual-pass LLM setup matched single-pass recall in one institution-specific study; its gain came from prompt changes, not the second call [20].
- TIDE 2.0 combines a model with regex matching in two stages and reports span recall of 0.88 in-domain and 0.77 on a second institution's corpus [21].

Design implication for `nyms` (an engineering inference, not a literature result): send the text with first-pass surrogates already in place, so the model never sees the original identifiers it would otherwise be sent; ask for spans over that text; map spans back to original offsets through the replacement table (the surrogate lengths differ, so keep an offset map); drop spans that fall wholly inside an existing surrogate; replace the rest and extend the mapping store. A local model avoids the question entirely; a remote model sees only residual leakage. Evaluate by the leakage rate before and after the second pass.

## Open questions

- Do the GLiNER PII checkpoints work on Danish? The cards do not say; a fixture test decides.
- CVR checksum rule and the CPR office's post-2007 assignment rules: read the primary specifications before encoding them.
- Name list source and licence: Danmarks Statistik tables versus a self-built list.
- Is a quasi-identifier policy (dates, amounts) in scope for v1, or a flag only?
- pii-codex, anonympy, Stanza, flair, trufflehog and PII-Bench were not assessed.

## REFERENCES

1. [Presidio supported entities](https://presidio.dataprivacystack.org/supported_entities/)
2. [personnummeret i cpr (CPR-kontoret)](https://admin.cpr.dk/media/12066/personnummeret-i-cpr.pdf)
3. [Denmark TIN, CPR and CVR number guide (lookuptax; commercial, secondary)](https://lookuptax.com/docs/docs/tax-identification-number/denmark-tax-id-guide)
4. [urchade/gliner_multi_pii-v1 model card](https://huggingface.co/urchade/gliner_multi_pii-v1)
5. [knowledgator/gliner-pii-base-v1.0 model card](https://huggingface.co/knowledgator/gliner-pii-base-v1.0)
6. [spaCy Danish models](https://spacy.io/models/da)
7. [DANSK and DaCy 2.6.0: Domain Generalization of Danish Named Entity Recognition](https://arxiv.org/pdf/2402.18209)
8. [Piiranha model card](https://huggingface.co/iiiorg/piiranha-v1-detect-personal-information)
9. [ai4privacy pii-masking-400k license](https://www.huggingface.co/datasets/ai4privacy/pii-masking-400k/blob/main/license.md)
10. [Philter paper (npj Digital Medicine)](https://link.springer.com/10.1038/s41746-020-0258-y)
11. [microsoft/presidio](https://github.com/microsoft/presidio)
12. [Presidio: languages](https://microsoft.github.io/presidio/analyzer/languages)
13. [scrubadub](https://github.com/LeapBeyond/scrubadub)
14. [Philter, UCSF (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7156708/)
15. [gitleaks](https://github.com/gitleaks/gitleaks)
16. [detect-secrets](https://github.com/Yelp/detect-secrets)
17. [Danmarks Statistik: names in the entire population](https://dst.dk/en/Statistik/emner/borgere/navne/navne-i-hele-befolkningen)
18. [Lovguiden: Datafordeler modernisation and parallel operation](https://lovguiden.dk/det-offentlige/klimadatastyrelsen/2026-06-25-datafordelerens-modernisering-paralleldrift-ophoerer-15-januar-2027) and [DAWA is closing](https://journals.aau.dk/index.php/gfp/article/view/9664)
19. [RedactOR: An LLM-Powered Framework for Automatic Clinical Data De-Identification](https://arxiv.org/html/2505.18380v1)
20. [Institution-Specific LLM Prompting Recovers PHI](https://arxiv.org/pdf/2608.17051)
21. [TIDE 2.0: an open, model-agnostic engine for keyed de-identification of clinical notes](https://arxiv.org/html/2610.07224v1)
