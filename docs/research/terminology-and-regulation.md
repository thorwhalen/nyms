# Terminology, regulatory framing and re-identification risk for nyms

*2026-11-08. Scope: vocabulary for the nyms API and docs, the sensitivity policy, and the entity taxonomy seam, with Danish specifics. Serves the design of reversible pseudonymisation of Danish and English text before it goes to an AI service.*

## Summary and recommendation

- Call what nyms does **pseudonymisation** (GDPR Art. 4(5)), never "anonymisation". The output stays personal data in the hands of anyone who can reach the mapping, and EDPB Guidelines 01/2025 say the data stays personal even if the additional information is held by someone else [1][2].
- The recipient-side picture is less settled: the CJEU (C-413/23 P, 4 Sept 2025) set aside the General Court and held, per commentary, that whether pseudonymised data is personal depends on the recipient's means. The EDPB says it is still reassessing its guidance in light of this [3][4]. nyms should therefore claim risk reduction, not legal anonymity, and state this in docs.
- Use the EDPB's own concepts as API vocabulary: **additional information** (the mapping store plus keys), **pseudonymisation domain** (who may see the mapping; for nyms: the local machine, not the AI provider) and **attribution** [1].
- Taxonomy: a small own core with three axes (identifier class, sensitivity tier, legal basis tag) that maps onto Presidio, Google DLP and HIPAA labels instead of adopting any one of them. Presidio has no Danish entity at all; Google DLP has only `DENMARK_CPR_NUMBER` [5][6]. Danish recognisers (CPR, CVR, reg.+account number, DK IBAN, DK phone, DK address) are therefore a real gap nyms fills.
- Policy object: a declarative, serialisable list of rules (entity or tier, action, threshold, allow/deny lists), evaluated after detection. Mirror Presidio's entity selection and score threshold, but add tiers and a fail-closed default for the highest tier.
- Report residual risk honestly: list what was detected, what was replaced, what categories are not covered, and a plain warning that free text keeps quasi-identifiers (roles, rare events, relationships) that no detector removes. Do not emit a numeric "risk score" without a validated model.

## 1. Definitions and how they differ

| Term | Core meaning | Reversible by design | Status under GDPR | Verdict for nyms |
|---|---|---|---|---|
| Pseudonymisation | Processing so data cannot be attributed to a person without additional information kept separately under technical and organisational measures (Art. 4(5)) [7] | Usually yes | Personal data (Recital 26) [1][7] | **The accurate name** |
| Anonymisation | Information not relating to an identifiable person, or rendered so the person is not identifiable; judged by "all the means reasonably likely to be used" (Recital 26) [7] | No | Outside GDPR | Never claim |
| De-identification | Umbrella term (US, HIPAA, ISO) for removing or transforming identifiers; ISO/IEC 20889:2018 classifies the techniques and relates them to re-identification risk [8] | Either | Not a GDPR term | Use only when citing ISO/HIPAA |
| Redaction | Removing or blacking out the value | No | Depends on residual data | A policy action, not the product |
| Masking | Partial obscuring (for example `****1234`) | Usually no | Depends | A policy action |
| Tokenisation | Replacing a value by a token, typically via a lookup vault; deterministic variants give the same token for the same input | Yes (vault) | Pseudonymisation when the vault is separated | nyms placeholder strategy |
| Surrogate generation | Replacing with a realistic fake of the same type (a fake name, a valid-looking number) so text stays natural | Yes via mapping | Pseudonymisation | nyms default for readable output |
| Keyed hashing / format-preserving encryption | Deterministic transformation under a secret key | Hash: no; FPE: yes with key | Pseudonymisation | Seam strategies |

Notes from the primary sources:

- Art. 4(5) and Recital 26 are quoted in the GDPR text on EUR-Lex [7]. Recital 26 says pseudonymised data attributable by additional information is information on an identifiable person, and that data protection principles do not apply to anonymous information.
- EDPB Guidelines 01/2025 were adopted 16 January 2025 as a version for public consultation (consultation 17 January to 14 March 2025) [1][2]. I could not confirm that a final version has been published. They state that pseudonymised data is personal "also" when data and additional information are not in the same hands, and that after the additional information is erased the data counts as anonymous only if the anonymity conditions are met [1].
- The **pseudonymisation domain** is the context (people, organisation, IT assets) in which the controller wants attribution to be precluded; it can be a single unit, one recipient, all authorised recipients, or all entities that might gain access [1, paras 35-38]. Additional information must be kept separate from it [1].
- On transformations, the guidelines name lookup tables with randomly generated pseudonyms, keyed one-way functions (HMAC) and ciphers with ciphertext indistinguishability as suitable building blocks, and require the pseudonymisation secrets to be kept confidential [1, paras 107-108]. This directly supports nyms' choice of random surrogates plus a protected mapping, and managed keys.
- ISO/IEC 20889:2018 places pseudonymisation under attribute selection and creation of pseudonyms (section 9.4) and deterministic encryption under cryptographic tools [8]. I could not read the normative definitions (paywalled); do not quote them.

## 2. Re-identification risk

Concepts (the EDPB's predecessor opinion on anonymisation, WP29 05/2014, names the same three; not re-fetched here, so treat as background): **singling out** (isolating a record), **linkability** (joining records about one person), **inference** (deducing an attribute). The UK ICO guidance of March 2025 treats identifiability as a spectrum, uses singling out and linkability as indicators, and applies a **motivated intruder** test: a reasonably competent person with access to public resources and no special skills; results should be recorded in a risk assessment [9][10] (secondary sources; the ICO text itself was not opened).

Table-oriented models: **k-anonymity** (each combination of quasi-identifiers appears in at least k rows), **l-diversity** (at least l distinct sensitive values per group), **t-closeness** (group distribution of the sensitive value close to the overall one). They assume a table with a fixed schema. I did not source these definitions in this session; they are textbook and well known.

What this means for free text:

- There is no schema, so k, l and t cannot be computed. Quasi-identifiers hide in prose: job title plus employer plus a dated event, a rare diagnosis, a court case, a distinctive writing style.
- Detection is probabilistic: a name or address the detector misses survives in the output. The honest quantity to report is detector coverage, not a privacy guarantee.
- Surrogates keep structure (gender of a name, a plausible date shift, same city size) which preserves utility but also leaks some information; consistency across a document is what makes linkage possible for the recipient.
- The recipient is an AI service that may log prompts. Under the EDPB view the data stays personal for the pseudonymising party regardless [1], so the user-facing claim is "identifiers replaced before leaving the machine", with the mapping staying local.

How nyms should report residual risk (recommendation, not sourced): a per-run report listing counts by entity type and tier, spans left because below threshold or allow-listed (so the user can review), categories the active detectors do not cover (for example "no detector for indirect identifiers"), whether the model-based second pass ran, and a fixed caveat sentence. No single scalar score. Offer a "motivated intruder" checklist for the user instead of a computed number.

## 3. Entity taxonomies in existing tools

| Tool | Granularity | Denmark | Notes |
|---|---|---|---|
| Presidio | 14 global types (PERSON, LOCATION, PHONE_NUMBER, EMAIL_ADDRESS, IBAN_CODE, DATE_TIME, CREDIT_CARD, URL, IP_ADDRESS, MEDICAL_LICENSE, ...) plus per-country types for about 20 countries [5] | None; Sweden and Finland present | Entities chosen per `analyze()` call; context words boost scores [5][11] |
| Google Sensitive Data Protection | Large catalogue with categories (GOVERNMENT_ID, PII, SPII, FINANCIAL_ID...) and a sensitivity level per infoType [6] | `DENMARK_CPR_NUMBER` only (SENSITIVITY_HIGH) [6] | Per-type sensitivity is a useful precedent for tiers |
| AWS Comprehend | About 20 universal types (NAME, ADDRESS, AGE, DATE_TIME, EMAIL, PHONE, IBAN, PASSWORD, USERNAME, AWS keys, card fields) plus country types (CA, IN, UK, US) [12] | None; English and Spanish only | Returns a score per span |
| HIPAA Safe Harbor | 18 identifier classes: names; geography below state; dates except year and ages over 89; phone; fax; email; SSN; medical record no.; health plan no.; account no.; certificate/licence no.; vehicle ids; device ids; URLs; IP; biometrics; face images; any other unique code [13] | n/a | Plus the "actual knowledge" condition; Expert Determination needs a documented finding that risk is "very small" for the anticipated recipient [13] |
| GDPR Art. 9 | Special categories: racial or ethnic origin, political opinions, religion or philosophical beliefs, trade union membership, genetic and biometric data for identification, health, sex life or orientation [7]. Art. 10 covers criminal convictions (law-enforcement-controlled processing) | n/a | Defines the legal sensitivity axis |

Recommended nyms taxonomy (extensible registry; each entity type carries `identifier_class`, `tier`, `art9`, and `aliases` mapping to Presidio, DLP and HIPAA names):

| Identifier class | Examples | Default tier |
|---|---|---|
| Credential | passwords, API keys, tokens, private keys (reuse `openloops.egress` patterns) | T0 block: replace always, never reversible-by-default, fail closed |
| Direct identifier | person name, CPR, passport, email, phone, street address, IBAN, account numbers, licence plates | T1 replace by default |
| Quasi-identifier | dates of birth and events, city, workplace, job title, age, rare facts | T2 replace or generalise by policy |
| Sensitive attribute | health, legal matter, finance amounts, religion, union, sexual life (Art. 9 flag) | T2 flagged; detection of the attribute is weak, so warn rather than claim removal |
| Organisation identifier | CVR number, company names | T2 (matters mostly for sole traders) |

Keep "amounts" and "dates" as separate configurable types: they are quasi-identifiers in finance and legal text but also the content the user wants the AI to reason on, so default to date shifting and amount retention with a warning.

## 4. Danish specifics

**CPR number.** Ten digits `DDMMYY-SSSS`: the first six are the date of birth; the last four are a serial part, whose last digit is odd for males and even for females; a century is derived from the serial part together with the year [14] (structure from secondary sources and common knowledge; the CPR office's own PDF returned 403, so confirm against it before coding). The old check: weights 4 3 2 7 6 5 4 3 2 1 over the ten digits, sum divisible by 11 [14][15]. From 1 October 2007 the CPR office issues numbers that need not satisfy it, because valid serials for some birth dates were exhausted [14][16]; failing numbers can belong to people born before 2007 (for example later immigrants whose birth date is unknown, often 1 January) [14]. I found no published count of the failing share, so any figure would be a guess. **Consequence: a nyms CPR detector must not require the mod-11 check.** Use pattern plus plausible date as the high-confidence rule; treat a passing check as a confidence boost only. Google DLP and Presidio-style recognisers that validate the checksum would miss new numbers [6][14].

**CVR number.** Eight digits, weights 2 7 6 5 4 3 2 1, sum divisible by 11; the first seven are a running number and the eighth a check digit [17][18]. Sources are secondary (Statistics Denmark and a library citing an Erhvervsstyrelsen page I could not open). Unlike CPR, CVR validation is safe as a confidence boost, but a bare eight-digit number is ambiguous, so require context words ("CVR", "cvr-nr", "SE-nr").

**Bank details.** Registreringsnummer (4 digits) plus kontonummer (up to 10 digits), and the Danish IBAN `DK` + 2 check digits + 4-digit reg. no. + 10-digit account (18 characters) [19]. One source gives 6 to 10 digits for the account part [19]; treat length as variable and pad. Sources are commercial; Finans Danmark was not reached.

**Other identifiers in legal and financial documents** (my knowledge, not verified in this session): phone `+45` with eight digits; postal code four digits followed by town; addresses as street, number, floor (`st.`, `1. th.`), door; NemKonto is a designation of a bank account (not a separate number); MitID is a login, not a fixed public identifier; also licence plates, VAT (`DK` + CVR), case numbers (sagsnummer), policy numbers, SKAT/tax references, and the Danish names with `-sen` endings and the middle-name tradition, which make NER on Danish names harder.

**Datatilsynet.** I found no Datatilsynet guidance specifically on pseudonymisation or on sending personal data to cloud AI services. It has guidance for public authorities on AI and a course on AI in the context of the GDPR (dates in 2026) [20]. Danish public bodies' own rules go further: one ministry's ChatGPT guideline bars entering personal data even when pseudonymised if other details permit identification [21]. The EDPB Opinion 28/2024 on AI models is the relevant European text [22]. Cite the EDPB, not Datatilsynet, for the legal framing, and say so.

## 5. What a sensitivity "policy" is in existing tools

- **Presidio**: entity selection at analysis time, a score threshold, allow-lists (values never flagged), deny-lists and ad-hoc recognisers (values always flagged), and context words that raise scores; I could confirm entity selection and context words from the page [11] and the rest from the navigation titles only.
- **Google DLP**: inspect config with a minimum likelihood and per-infoType rules (exclusion and hotword rules); sensitivity levels per infoType [6] (likelihood semantics not read).
- **AWS Comprehend**: a score per span and the caller filters [12].

Recommended `Policy` object (declarative, serialisable, validated by a schema, with a documented default):

```
Policy:
  name: str
  rules: list of Rule      # first match wins, evaluated AFTER detection
  default_action: replace | warn | keep
  fail_closed_tiers: [T0]  # refuse to send if detected and unresolved
  allow: list of values/patterns   # never replace
  deny: list of values/patterns    # always replace
Rule:
  match: entity type | tier | art9 flag
  min_score: float
  action: surrogate(strategy) | placeholder | mask | redact | keep | warn
  reversible: bool
```

Reasons: select entities after detection (not before), so the report can say what was seen and not replaced; keep detectors running for all types and decide in the policy, so adding a tier never needs re-detection; allow-lists beat deny-lists only when explicit order says so; keep thresholds per rule rather than global, since Danish recognisers will have very different precision than name NER.

## Open questions

- Is a final version of EDPB Guidelines 01/2025 published, and how do they change after C-413/23 P? Check the EDPB site before the first release.
- What share of issued CPR numbers fail mod-11, and what is the century rule exactly? Ask the CPR office or read its documentation (the PDF needs a browser fetch).
- Do we want Art. 9 flags as a tier or a separate boolean? Both appear above; the boolean is more faithful to the law.
- Which Danish name and address NER is good enough for the model-based pass? Out of this report's scope.
- ICO text and WP29 05/2014 were not read as primary documents.

## REFERENCES

1. [EDPB, Guidelines 01/2025 on Pseudonymisation, adopted 16 Jan 2025 (PDF, consultation version)](https://www.edpb.europa.eu/system/files/2025-01/edpb_guidelines_202501_pseudonymisation_en.pdf)
2. [EDPB, Guidelines 01/2025 on Pseudonymisation, consultation page](https://www.edpb.europa.eu/our-work-tools/documents/public-consultations/2025/guidelines-012025-pseudonymisation_en)
3. [EUR-Lex, Official Journal notice on Case C-413/23 P, EDPS v SRB](https://eur-lex.europa.eu/eli/C/2025/5551/oj/eng)
4. [EDPB, stakeholder event discussion paper, December 2025](https://www.edpb.europa.eu/system/files/2025-12/stakeholder-event-20251212-discussion-paper_en.pdf); commentary: [Clifford Chance, Pseudonymized data after EDPS v SRB](https://www.cliffordchance.com/insights/resources/blogs/talking-tech/en/articles/2025/09/pseudonymized-data-after-edps-v-srb.html)
5. [Presidio, supported entities](https://presidio.dataprivacystack.org/supported_entities/)
6. [Google Sensitive Data Protection, infoType reference](https://docs.cloud.google.com/sensitive-data-protection/docs/infotypes-reference)
7. [EUR-Lex, Regulation (EU) 2016/679 (GDPR)](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679) (Recital 26 read; Art. 4(5) and Art. 9 not extracted by the fetch, cited from the regulation)
8. [DIN, ISO/IEC 20889:2018 table of contents](https://www.din.de/de/mitwirken/normenausschuesse/nia/veroeffentlichungen/wdc-beuth:din21:298672377/toc-3021025/download); [ANSI/BSI preview](https://webstore.ansi.org/preview-pages/BSI/preview_30331888.pdf)
9. [Taylor Wessing, New ICO guidance on anonymisation and pseudonymisation](https://www.taylorwessing.com/de/global-data-hub/2025/spotlight-on-the-uk-data-landscape/gdh---new-ico-guidance-on-anonymisation-and-pseudonymisation)
10. [SCL, ICO publishes anonymisation guidance](https://www.scl.org/ico-publishes-anonymisation-guidance/)
11. [Presidio, analyzer documentation](https://presidio.dataprivacystack.org/analyzer/)
12. [AWS, Amazon Comprehend: detecting PII entities](https://docs.aws.amazon.com/comprehend/latest/dg/how-pii.html)
13. [eCFR, 45 CFR 164.514 (de-identification)](https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/title-45?part=164&section=164.514)
14. [LookupTax, Denmark TIN: CPR and CVR number guide](https://www.lookuptax.com/docs/tax-identification-number/denmark-tax-id-guide) (secondary); CPR office PDF not readable: [personnummeret i CPR](https://admin.cpr.dk/media/12066/personnummeret-i-cpr.pdf)
15. [cprr (R package), mod11 check for CPR numbers](https://github.com/anhoej/cprr)
16. [Wikipedia, Personal identification number (Denmark)](https://en.wikipedia.org/wiki/Personal_identification_number_(Denmark)) (secondary, low authority)
17. [Statistics Denmark, CVR-nr variable documentation](https://www.dst.dk/da/Statistik/dokumentation/Times/moduldata-for-formue-og-gaeld/pensionsformue/cvr-nr)
18. [HL7 FHIR DK Core, CVR identifier](https://build.fhir.org/ig/hl7dk/dk-core/StructureDefinition-dk-core-cvr-identifier.html); [CVR (Elixir library) docs](https://hexdocs.pm/cvr/CVR.html)
19. [Dinero, IBAN-nummer](https://dinero.dk/ordbog/iban-nummer.md); [Wise, IBAN in Denmark](https://wise.com/dk/iban/denmark)
20. [Datatilsynet, Kunstig intelligens i kontekst af databeskyttelsesforordningen](https://www.datatilsynet.dk/Media/638985421478983569/Kunstig%20intelligens%20i%20kontekst%20af%20databeskyttelsesforordningen.pdf)
21. [Ministry guideline on employees' use of ChatGPT](https://cdn1.gopublic.dk/skimintra/Media/639136716055644305/retningslinjer-for-medarbejderes-brug-af-chatgpt-i-departementet.pdf)
22. [EDPB, Opinion on AI models (28/2024)](https://www.edpb.europa.eu/news/edpb-opinion-on-ai-models-gdpr-principles-support-responsible-ai_da)
