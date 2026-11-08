# Vocabulary: the expert term, and the phrasing it replaces

| Use | Instead of | Meaning |
|---|---|---|
| pseudonymisation | anonymisation, redaction, "mapping to keys" | replacing identifiers so the data cannot be attributed without separately held additional information (GDPR Art. 4(5)); the data stays personal |
| surrogate, pseudonym | key, token, placeholder, alias | the string that replaces a value; a pseudonym when it stands for a person |
| surrogate strategy | "how the mapping works" | the rule that produces a surrogate for a new value: counter, keyed hash, random vault, user alias |
| mapping store | "the keys", the vault | surrogate to original, per project; the additional information |
| key | password, secret | the project's secret bytes: keyed hashing, encryption of the store |
| additional information | the mapping | the EDPB's term for mapping plus key |
| pseudonymisation domain | "who can see it" | the context in which attribution is precluded; for nyms, outside the local machine |
| detector | regex, rule, recogniser | `text -> spans`; deterministic in v1 |
| span | match, hit | half-open character interval, entity type, score, detector |
| policy | sensitivity settings, "what counts as sensitive" | which spans are replaced, decided after detection |
| tier | level | 0 block, 1 replace by default, 2 policy decides |
| re-identification | de-anonymisation, un-redaction, restoring | putting originals back into text that carries surrogates |
| leak check | scan | originals of the project found in outgoing text |
| keyed hashing | hashing | HMAC under a secret key; an unkeyed hash of a low-entropy identifier is reversible by enumeration |
| format-preserving encryption | "keep it looking like a number" | encryption whose output has the input's alphabet and length (NIST FF1); a replacement strategy, not built |
| tokenisation | random mapping | random surrogates with a vault (the PCI DSS sense) |
| named-entity recognition (NER) | "the AI pass" | model-based detection of names, places, organisations |
| re-identification risk | "how safe is it" | singling out, linkability, inference; reported as coverage, never as a score |
