# Pipeline architecture and agent practice for a reversible pseudonymisation toolkit

*2026-11-08. Scope: how existing de-identification toolkits and LLM privacy gateways structure their pipeline, what is known about placeholders surviving an LLM, and how `nyms` should expose itself to coding agents, test itself and state its residual risk. Serves the overall shape of `nyms` (facade, seams, surfaces) and its dev skills. Search was limited: several products named in the brief (Private AI, Nightfall, Protecto, Lakera, the n2c2/i2b2 system designs) were not verified and are marked as such.*

## Summary and recommendation

- Every toolkit checked splits the work into detect (spans with type and score), transform (an operator per entity type) and, optionally, reverse. Presidio makes this explicit with separate analyzer and anonymizer packages and a deanonymizer that only inverts reversible operators [1]. `nyms` should copy the split but make reversal a first-class, stored mapping rather than a property of one operator.
- Presidio has no sessions: it "does not store or maintain stateful sessions" [1]. Cross-document consistency is therefore the main thing a pseudonymisation toolkit must add. Gateways that do it keep a persistent store (SQLite with a seed and a retention period [8], a JSON mapping file [9], LLM Guard's Vault [3]), and every one of them warns that the store itself is sensitive.
- The best evidence on round trips is one 2026 vendor benchmark (single author, not peer reviewed, Russian and UK English): plain bracketed placeholders like `[PERSON_1]` were altered by models in 1 of 8,099 occurrences, against 101 of 5,099 for XML-style tags; restoration reached 99.99% in English with a tolerant restorer [5]. Treat as strong hint, not settled fact, and rerun on Danish.
- Recommendation: default surrogate form is a bracketed typed token with a per-project counter (`[PERSON_1]`), with a readable-name surrogate strategy as an opt-in seam; restoration is tolerant (case, spacing, dropped bracket) and reports invented and unmatched tokens instead of hiding them; the mapping is keyed to a project, not a document.
- Agent surface: a small set of verbs (`pseudonymise`, `reidentify`, `review`, `policy`) over one facade, with a mandatory review step before anything leaves the machine and a fail-closed default. Existing MCP privacy tools show the shape but none documents a real review gate [9].
- Residual risk is stated by `nyms` per run (counts by detector, what was not checked); the client-facing explanation of what a deterministic pass cannot catch lives in the separate risk guide.

## 1. How mature toolkits structure the pipeline

| Tool | Pipeline shape | Done well | Pain points or limits | Verdict for `nyms` |
|---|---|---|---|---|
| Presidio [1][2] | Analyzer returns `RecognizerResult` (type, start, end, score); anonymizer applies an operator per entity type; deanonymizer inverts. Operators: replace, redact, mask, hash, encrypt, custom, keep. Engine has `add_anonymizer` / `add_deanonymizer` | Clean span contract in character offsets; pluggable operators; documented overlap rules (higher score wins, larger span wins on containment, partial overlaps anonymised separately) [1] | Only `encrypt` has a built-in inverse; a reversible custom operator needs a matching deanonymizer [1][2]; reversal depends on saved `result.items` offsets, so editing the text in between breaks it (inferred from a third-party doc [2]); no session state [1]; `presidio-structured` is alpha (0.0.8) [4] | Copy: span contract, operator registry, overlap rules. Do not copy: reversal tied to per-call offsets |
| Google Cloud DLP [6] | De-identify and re-identify with the same transformation config; `CryptoReplaceFfxFpeConfig` gives a deterministic format-preserving surrogate for a given key and context | `surrogate_info_type` prefixes the surrogate (`NAME(3):abc`) so inspection can find it again at re-identification; recommends `CryptoDeterministicConfig` when alphabet and length need not be preserved [6] | FPE input must be ASCII and at least two characters [6], which excludes Danish letters (æ, ø, å) unless mapped; the marker infoType must not occur naturally in the data [6] | Copy: a recognisable surrogate marker idea, and "deterministic keyed" as a strategy. Treat FPE as one strategy, not the core |
| AWS Comprehend [7] | `DetectPiiEntities` returns type, score and character offsets; redaction is an async batch job that masks with asterisks | Simple, offset-based, typed | English and Spanish only; redaction is irreversible; 100 KB per real-time document [7] | Not a model for reversibility; Danish is unsupported |
| Philter (UCSF) [10] | Rule-based plus statistical filters over clinical notes; certified audit of the production pipeline | High recall as design goal (reported 99.46% recall on its own test corpus) [10] | Clinical and English-oriented; its filter sets are curated, not general | Copy: recall-first stance, evaluating on an annotated corpus |
| LLM Guard [3] | `Anonymize` input scanner stores replacements in a Vault; `Deanonymize` output scanner restores from the Vault | The right two-ended shape for LLM use; `use_faker` option for readable surrogates [3] | Entity detection documented as English-specific [3] | Copy: Vault as the shared state between the two ends |
| OpaquePrompts [11] | Sanitise prompt (PERSON_1 style tokens), call LLM, de-sanitise response, inside an attested trusted execution environment | One-line wrapper integration | Hosted, API-key service; I did not verify its current status [11] | Copy: the wrapper ergonomics; local-only is a stronger default |

Not verified here: Private AI, Nightfall, Protecto, Lakera, and the n2c2/i2b2 system designs. The recurring theme from the benchmark literature [5] is that detectors differ most in leak rate, not in transformation.

## 2. The round-trip problem

**Placeholder forms.** The one benchmark found compares three: XML-style tags, `<Name_1>` and plain `[PERSON_1]` [5]. Plain brackets were altered least (1/8,099 and 4/8,382 occurrences on two held-out sets), but the author says the two sets disagree at the answer level, so format is not established as the cause; alterations concentrate in a few answers [5]. Invented placeholders occurred for one of two tested models (85 in Russian, 21 in English, none for the other) and cannot be restored [5]. A privacy-utility study notes that reinserting entities can reduce response coherence [12]. I found no source on `PERSON_1` versus `PERSON_11` confusion; this is a design risk by construction (prefix match) and should be tested directly, for example by always matching the longest token and by delimiting tokens.

**Altered surrogates.** The benchmark's restorer tolerates case changes, extra spaces, words inside the brackets, a dropped bracket, and adjacent tokens written without a space [5]. Its largest failures were in Russian inflection of names (188 of 289 checked failures) [5]. Danish inflects less than Russian but adds genitive `-s` (`[PERSON_1]s`), definite endings on organisation names, and compounds; the restorer should accept a suffix after the token and re-attach it.

**Consistency across documents and sessions.** The benchmark's engine propagates a detected name to every mention, including later messages in the session, and found that merging two distinct people into one placeholder is worse than a leak [5]. MCP Conceal keeps a seeded consistent mapping in SQLite with a retention period and warns that short retention makes recurring data inconsistent [8]. Recommendation: the mapping domain is a project (a named store), keyed on a normalised form of the identifier, with a seed or key held by `config2py`; `dol` is the store facade.

| Surrogate strategy | Survives LLM | Readability for model | Verdict |
|---|---|---|---|
| Bracketed typed token `[PERSON_1]` | Best measured [5] | Model treats as opaque entity | Default |
| XML-style tag | Worse measured; parser sensitive [5] | Same | Avoid |
| Readable fake name (Faker, `use_faker` [3]) | Not measured; model may transform or "correct" it | Best fluency | Opt-in strategy; needs fuzzy restoration and collision checks |
| Keyed deterministic code (hash, FPE) [6] | Fine for ids | Poor for names | Use for structured identifiers (numbers, account ids) |

## 3. Span and document handling

- Presidio and Comprehend both report character offsets [1][7]. Use Unicode code-point offsets in the NFC-normalised text, store the normalisation applied, and never mix with byte or token offsets. Python `str` indexing is code-point based, so this is the cheap choice; JavaScript surfaces use UTF-16 units and need a conversion layer (estimate of risk: any emoji or combining mark shifts offsets).
- Apply replacements right to left or build the output in one pass from a sorted, overlap-resolved span list (Presidio's rules are a good default [1]), and record both source and output offsets in the audit record.
- Structured input: `presidio-structured` analyses columns or JSON paths (for example `users.name`) and then anonymises values in flagged columns [4]. Do the same: detect per column and per key, decide by schema rather than per cell, keep types and delimiters intact.
- Documents: operate on the text layer and keep structure separate. Markdown and plain text can be rewritten in place; DOCX and PDF should be handled as a run list or extracted text with a map back to runs. I found no tool that documents round-tripping a PDF text layer; treat PDF as one-way extract (pseudonymised text out, re-identified text in) until shown otherwise.
- File trees: write a sibling tree and a manifest of path, hash, span count and mapping version, so the whole tree can be re-identified or verified. File names and paths are identifiers too (the in-house `openloops.egress` path rewriting is a precedent).
- Provenance: an audit record per run with detector, rule or model version, span (source offsets), type, surrogate id, and policy. Redact-MCP's audit log shows the trap: it holds real values and so is itself sensitive [9]. Store hashes of originals in the audit record and keep real values only in the encrypted mapping.

## 4. Agent-facing practice

Observed shapes: Redact MCP exposes obfuscate, deobfuscate, read-file, add/remove mapping, show mappings and audit-log tools plus hooks (a SessionStart instruction and a PostToolUse warning when raw output contains known values) [9]; Philter MCP forwards redaction to a self-hosted Philter [13]; a Claude Code hook design screens MCP tool output with a model-based filter and does not stop a server sending the data in the first place [14]. Their stated limit is the same: the leak check is a warning, not a block [9]. I found no tool documenting a human review gate.

Proposed `nyms` agent surface (one facade, thin adapters):

| Verb | Contract | Safety property |
|---|---|---|
| `pseudonymise(path or text, project, policy)` | Returns pseudonymised text and a report; never returns originals | Deterministic pass runs first; fails closed if a detector errors or a file type is unknown |
| `review(run_id)` | Lists spans grouped by type with surrounding context, flags low-confidence and unchecked regions; accepts add, remove, merge | The only way to mark a run `approved` |
| `reidentify(text, project)` | Restores tokens; returns restored text plus lists of unmatched, invented and ambiguous tokens | Never guesses silently |
| `policy(get/set)` | Types to replace, strategy per type, strictness, allow-list | Policy lives in a file in the project, diffable |

Rules for the dev skill: the agent must call `pseudonymise` before any content reaches a model, must not send unapproved output to a service, must treat a non-empty "unchecked" list as a stop and ask, and must never read the mapping store. Make the safe path the default: the send helper (`aix` wrapper) refuses unapproved runs, a leak check scans outgoing text for known originals (as Redact's hook does, but blocking rather than warning), and the CLI (`cw`) mirrors the verbs.

## 5. Testing practice

- Synthetic fixtures: invented Danish and English documents (a lease, a bank statement, a clinic letter) with names containing æ, ø, å, addresses, phone numbers, Danish civil registration numbers (format DDMMYY-SSSS, from general knowledge, not checked here), IBANs, emails, and tricky cases: names that are common words, a person who shares a surname with a street, genitive `-s`.
- Golden files: input, detected spans (JSON) and pseudonymised output committed; diffs show detector regressions. Annotate fixtures once, reuse for precision and recall; report leak rate (whole value left), which the benchmark treats as the primary metric [5].
- Leakage test: for every fixture, assert no original identifier (normalised, case-insensitive, also with separators removed) occurs in the output.
- Property-based round trip with Hypothesis [15]: generate text interleaved with identifiers from a generator and assert `reidentify(pseudonymise(x)) == x`, plus idempotence, offset validity and token-prefix safety (`[PERSON_1]` versus `[PERSON_11]`). Hypothesis's own docs page I fetched does not state the round-trip pattern, so this is my design, not a documented recipe.
- LLM-in-the-loop regression corpus: saved model answers, including answers with altered, dropped and invented tokens, so the restorer is tested without network access.
- Cross-document tests: same person in two documents yields one token; two people with one surname yield two.

## 6. Residual risk, honestly

A deterministic pass catches patterns (numbers, emails, ids) and listed names; it misses names it has not seen, indirect identifiers (a rare job plus a small town), and context that identifies without any identifier. Related work finds LLM agents can infer identities from weak cues [16]. `nyms` should therefore print, per run: counts by type and detector, regions not checked (unsupported file parts, images), what the optional model pass found beyond the deterministic one, and the sentence "pseudonymised, not anonymous: the mapping is a key to the original". The toolkit owns the numbers and the gates; the client-facing guide owns the explanation, the legal framing (pseudonymised data stays personal data under GDPR) and the advice on what not to send. Line to draw: if it can be computed from a run, `nyms` reports it; if it needs judgment about a person's situation, the guide covers it.

## Open questions

- Does the bracketed-token advantage hold for Danish and for current frontier models? Rerun the benchmark method [5] on a Danish fixture set; the cited result is one vendor's, single author.
- Which readable-surrogate method keeps both fluency and restorability (and does it leak via gender or ethnicity cues)?
- Mapping store at rest: encrypted file via `dol` plus a key from `config2py`, or an OS keychain? Who may read it, given an agent runs the tool?
- Is a review gate needed for every run, or only when low-confidence or unchecked regions exist?
- Private AI, Nightfall, Protecto, Lakera, n2c2/i2b2 designs: not verified; worth a second pass if comparison against commercial detectors matters.

## REFERENCES

1. [Presidio Anonymizer documentation](https://presidio.dataprivacystack.org/anonymizer/)
2. [Presidio sample: custom operators and deanonymization (mirror: tessl.io docs for presidio-anonymizer)](https://tessl.io/registry/tessl/pypi-presidio-anonymizer/files/docs/deanonymization.md)
3. [LLM Guard Anonymize scanner](https://protectai.github.io/llm-guard/input_scanners/anonymize) and [Deanonymize scanner](https://protectai.github.io/llm-guard/output_scanners/deanonymize)
4. [presidio-structured on PyPI](https://pypi.org/project/presidio-structured/)
5. [Beskorovainyi V. Reversible Pseudonymisation of Documents Sent to External LLMs: an Open Bilingual Benchmark and an Engine. arXiv:2610.34012 (Oct 2026)](https://arxiv.org/html/2610.34012)
6. [Google Cloud DLP: CryptoReplaceFfxFpeConfig reference](https://cloud.google.com/python/docs/reference/dlp/latest/google.cloud.dlp_v2.types.CryptoReplaceFfxFpeConfig)
7. [Amazon Comprehend: Detecting PII entities](https://docs.aws.amazon.com/comprehend/latest/dg/how-pii.html)
8. [MCP Conceal (gbrigandi/mcp-server-conceal)](https://github.com/gbrigandi/mcp-server-conceal)
9. [Redact MCP (r3352/redact-mcp)](https://github.com/r3352/redact-mcp)
10. [Norgeot B, et al. Protected Health Information filter (Philter), npj Digital Medicine 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7156708/)
11. [LangChain blog: OpaquePrompts x LangChain](https://blog.langchain.com/opaqueprompts-x-langchain-enhance-the-privacy-of-your-langchain-application-with-just-one-code-change)
12. [Balancing Privacy and Utility in Personal LLM Writing Tasks, PrivateNLP 2025](https://aclanthology.org/2025.privatenlp-main.3.pdf)
13. [Philter MCP](https://philterd.ai/philter-mcp/)
14. [Preventing accidental PII exposure in Claude Code MCP workflows (Daymark)](https://www.usedaymark.io/blog/preventing-pii-exposure-mcp-tool-outputs-claude-code)
15. [Hypothesis documentation](https://hypothesis.readthedocs.io/en/latest/)
16. [From Weak Cues to Real Identities: Evaluating Inference-Driven De-Anonymization in LLM Agents, arXiv 2603.18382](https://arxiv.org/pdf/2603.18382)
