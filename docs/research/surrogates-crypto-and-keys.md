# Surrogate generation, cryptography, readable encodings, mapping store and key management for nyms

*2026-11-08. Scope: the surrogate generator, the reversible mapping store and key management seams of `nyms`. Serves the design of those three seams and their default and replacement implementations.*

## Summary and recommendation

- Default surrogate generator: a **vault of random, readable tokens** (tokenisation: each original gets a random surrogate, recorded in a lookup table). It is reversible only through the store, immune to dictionary attack because the surrogate carries no information about the original, and it is what the EDPB describes as the lookup-table class of pseudonymisation [1].
- Optional strategy for cross-document linkability without a growing vault: **keyed hashing (HMAC-SHA-256) with a per-project key**, rendered into words. Never an unkeyed hash and never a "salt" for low-entropy identifiers such as a CPR number (about 10^10 candidates at most; enumeration takes seconds) [1].
- Format-preserving encryption (FPE) is a niche replacement, not a default: only FF1 survives in NIST's second public draft of SP 800-38G Rev. 1 (3 Feb 2025); FF3 and FF3-1 were dropped after cryptanalysis [2]. The maintained Python `ff3` library implements only the withdrawn algorithms [3].
- Readable encoding: for LLM round-tripping, prefer **ordinary-looking, word-shaped surrogates** (a name for a name) drawn from a large word list with a checksum-free, case-stable form. Rank: random vault of name-shaped tokens > EFF-style word lists > PGP words/BIP-39 > proquints/Bubble Babble > Koremutake-style syllables. Digits-only or opaque strings are the most fragile.
- Mapping store: a `dol`-style `MutableMapping` of records (type, original, surrogate, spans, document, time), encrypted at rest with Fernet or AES-GCM, key held outside the store (OS keyring by default, passphrase via Argon2id or `age` as replacements). Lose the key or the store and re-identification is impossible, by design.
- Keys: one master key per project in the OS keyring, per-purpose subkeys via HKDF, envelope encryption for rotation, and a documented backup. Keep this "additional information" apart from the pseudonymised text, as GDPR Art. 4(5) and the EDPB require [1].

## 1. Surrogate strategies

Definitions. *Pseudonymisation*: processing so that data cannot be attributed to a person without additional information kept separately (GDPR Art. 4(5)); pseudonymised data stays personal data [1]. *Tokenisation*: replacing a value by a random surrogate and keeping the mapping in a protected vault (the PCI DSS usage). *Keyed hashing*: a hash with a secret key (HMAC, or BLAKE2b in keyed mode). *Format-preserving encryption (FPE)*: encryption whose ciphertext has the same format (alphabet and length) as the plaintext. *Re-identification*: recovering originals, here by the vault or by guessing.

The EDPB 01/2025 guidelines (adopted 16 January 2025 for consultation; the text I read is the consultation version, final status not verified) split transformations into two classes: cryptographic algorithms (MACs/keyed one-way functions, or encryption when reversal is needed) and lookup tables with random pseudonyms. All of them count as pseudonymisation provided the "pseudonymisation secrets" (keys or tables) stay separate and protected, and secrets need enough entropy against brute force. They note that a bare SHA-256 of a name is reversible by hashing known names, and that where hash functions are building blocks, password-grade hashes such as Argon2 are advisable [1].

| Strategy | Deterministic | Reversible | Format kept | Cross-document linkable | Dictionary-attack resistant | Readable (human / LLM) | Verdict |
|---|---|---|---|---|---|---|---|
| Plain numbering (PERSON_1) | per run | via map | no | only if map persisted | yes (no information) | high / high, but collides with real text and invites arithmetic confusion | Good baseline for debugging; weak for fluent text |
| User-chosen alias | yes | via map | by choice | yes | yes | high / high | Offer as override on top of any strategy |
| Random token + vault | no (stored once) | via vault | by token design | yes through the vault | yes | depends on encoding | **Default** |
| HMAC-SHA-256 / keyed BLAKE2b, truncated | yes | no (needs a candidate list or vault) | by encoding | yes, with the same key | yes if key is secret and strong | depends on encoding | Optional strategy; handle truncation collisions by extending length or falling back to the vault |
| Unkeyed hash, or hash with public salt | yes | by enumeration | no | yes | **no** for low-entropy values (CPR, phone, names) | n/a | Reject; offer no option |
| FPE (FF1) | yes per key and tweak | yes, by decryption, no vault | yes | yes | yes, if domain is large | digits stay digits | Replacement for numeric identifiers only; domain must be large (the original standard required 100 minimum, recommended 10^6) [2] |
| AES-SIV (RFC 5297), deterministic authenticated encryption | yes | yes, without vault | no (binary output) | yes | yes | needs encoding; output is longer than input | Replacement when the store must be avoided; `cryptography` provides `AESSIV` [4][5] |
| Seeded Faker per entity (seed = HMAC of the original) | yes | via map | realistic | yes | yes if the seed is keyed | very high / high | Good "looks real" renderer; MIT, maintained (40.44.0, Oct 2026) [6] |

Notes. Salt versus key: a salt is not secret and only defeats precomputed tables; it does nothing against a targeted enumeration of a small domain, whereas a secret key does. A CPR number has at most about 10^10 values (date of birth plus a four-digit serial; the exact valid count is an estimate), so an unkeyed or publicly salted hash falls to enumeration. Truncation: with n output bits, expect collisions near 2^(n/2) distinct values (birthday bound); a vault checks for collisions at insertion, a pure hash cannot.

FF3 history. SP 800-38G (2016) defined FF1 and FF3. FF3 was broken by Durak and Vaudenay (2017), repaired as FF3-1 (draft Rev. 1, 2019), and Beyne's 2021 attack covered FF3-1 too; the second public draft (Feb 2025) specifies FF1 only [2]. NIST's page states FF3 was removed; it does not say so explicitly for FF3-1, but the abstract names FF1 alone [2].

Libraries. `ff3` 1.0.3 (Apache-2.0, last release 26 Jan 2026; repository `mysto/python-fpe`) implements FF3 and FF3-1 only, and its own README states FF1 is out of scope, that both algorithms are now withdrawn, and that patent claims on FF1 exist [3]. `pyffx` 0.3.0 (MIT, last release May 2019, unmaintained) implements a simplified Feistel construction rather than a NIST algorithm [7]. I did not verify a maintained Python FF1 package; treat FPE as an area needing the `cryptography` primitives plus a self-written FF1, or none. `cryptography` 50.0.2 (Apache-2.0 or BSD-3-Clause, Sept 2026) is actively maintained [4].

## 2. Readable encodings

Bits per word is log2 of the list size; I counted the EFF and BIP-39 lists from their published files.

| Scheme | Unit and list size | Bits per unit | Licence | Python | Verdict for nyms |
|---|---|---|---|---|---|
| EFF large wordlist | 7,776 words (6 dice) | 12.925 | CC BY 3.0 | none needed (text file) | Best general encoding: common words, distinct, edit-distance 3 |
| EFF short lists 1 and 2 | 1,296 words each | 10.34 | CC BY 3.0 | text files | Shorter words; list 2 has unique 3-letter prefixes |
| BIP-39 English | 2,048 words | 11.0 | MIT (BIPs repository) | `mnemonic` 0.21 (MIT, Jan 2024) [8] | Distinct 4-letter prefixes; do not use its checksum feature as a surrogate property |
| PGP word list | 2 lists of 256 (even/odd position) | 8 | public text (verify before bundling) | none verified | Two lists catch transposition; many words per hash |
| Proquint | 5-letter CVCVC unit | 16 | MIT-style (verify) | `proquint` 0.2.1 (2017) | Pronounceable but not word-like; an LLM may reformat it |
| Bubble Babble | 5-letter groups | about 16 per pair | BSD-style (verify) | `bubblepy` 1.0 (2016) | Looks like noise to a model |
| humanhash | 256-word list | 8 | public domain (3) / unknown (original) | `humanhash3` 0.0.6 (2017) | Stale; trivial to reimplement |
| codenamize | adjectives plus nouns | tunable | MIT | `codenamize` 1.2.3 (2018) | Stale but small |
| petname (Docker-style) | adjective-noun lists | tunable | Apache-2.0 | `petname` 2.9 (Feb 2026) [9] | Maintained; good for non-person entity labels |
| what3words | 3 words for a 3 m square | proprietary mapping | proprietary | API | Not suitable (closed, geographic) |
| Mnemonic Major System | digits to consonant sounds | not a hash encoding | in-house `hm` | in-house | Reversible for digits, producing words; ambiguous in the word-to-digit direction, so keep it a rendering aid, not the vault key |
| Koremutake / FIPS 181 (APG) | syllables | about 7 per syllable | Koremutake open; FIPS 181 was withdrawn by NIST (from memory, not re-verified) | none verified | Pronounceable but invented words; low readability |

Which survives LLM paraphrase. This is my reasoning, not a measured result, and it should be tested on the target models: models copy common words and capitalised, name-like tokens verbatim far more reliably than punctuation-heavy or digit-heavy strings, and they sometimes normalise case, hyphenation or spacing. So: one token, no internal punctuation, a capitalised word-shaped form for a person, stable case, and a re-identification pass that tolerates case and diacritic differences and detects near-misses by edit distance. Multi-word surrogates (two or three words) survive if hyphenless and kept as a fixed phrase; a four-word mnemonic is more likely to be truncated.

Looking like what it replaces without lying. Give the surrogate the right shape (a plausible Danish forename plus surname for a person, a similar-magnitude number for an amount, a valid-looking but checksum-invalid number for a CPR or CVR) and record in the output envelope that it is a surrogate. A realistic fake that happens to match a real person is a risk, so draw names from a list and check against the real names present in the document. Do not make fabricated numbers pass real checksums.

## 3. The mapping store

Each record: entity type, original, surrogate, character spans, document id, time, strategy and key id. Rules: unique constraint on (type, surrogate) so re-identification is unambiguous; a store of records is personal data and a pseudonymisation secret in the EDPB's terms [1]; encrypt values at rest (Fernet from `cryptography` is AES-128-CBC with HMAC and is simplest; AES-GCM with a random 96-bit nonce per record is the direct alternative; `age` via `pyrage` 1.4.0, MIT, Aug 2026, suits file-level encryption to a recipient key [4][10]); keep keys out of the store directory; write as an append-only log (new lines never edit old ones) and compact explicitly; hold the index in memory after decrypt. Fit with `dol`: the store is a `MutableMapping` keyed by surrogate or record id, wrapped with value codecs for encryption and JSON, so backends (file, SQLite, S3) swap without touching logic.

Loss: lose the key and the store is unreadable; lose the store and the key can only re-derive HMAC-style surrogates, not originals. State this in the README, and support an explicit export of an encrypted backup.

## 4. Key management

Derivation: Argon2id (`argon2-cffi` 25.1.0, MIT, June 2025) or scrypt for passphrases; HKDF for subkeys from a master key (separate keys for encryption, HMAC and per-project domain separation) [11]. Storage: the `keyring` package (25.7.0, MIT, Nov 2025) uses macOS Keychain, Windows Credential Locker or Secret Service, with a file-based fallback to avoid [12]; `config2py` can supply the resolution order in-house. Granularity: one key per project (per-document keys destroy cross-document linkability, and are the right choice only when linkability is unwanted). Rotation: envelope encryption, a master key wrapping a data key per store, so rotation re-wraps one key; re-keying the vault rewrites records under the new key id. Keyed-hash surrogates cannot be rotated without changing every surrogate, so rotation there means a new pseudonymisation epoch. Backup: an offline copy of the wrapped key and a printed recovery passphrase. NIST SP 800-57 Part 1 is the reference for key lifecycle and cryptoperiods; I did not retrieve it for this report, so its specific recommendations are unverified here. The EDPB says additional information must be kept separate with technical and organisational measures, and suggests secret sharing or hardware security modules as extra protection [1].

## 5. Recommended defaults and replacements

| Seam | Default | Replacement the seam must allow |
|---|---|---|
| Surrogate generator | Random vault tokens, name-shaped for names, from word lists; callable `generate(entity, context) -> str` | HMAC strategy, seeded Faker renderer, FPE (FF1) for numerics, AES-SIV, user aliases |
| Mapping store | Encrypted `MutableMapping` over a local file, append-only log | Any `dol` backend, SQLite, remote store |
| Key management | Master key in OS keyring, HKDF subkeys, envelope wrapping | Passphrase plus Argon2id, `age` recipient, environment variable (CI), HSM or external KMS |

## Open questions

- Is the final EDPB 01/2025 text (post-consultation) changed on hashing and key separation? Only the consultation PDF was read.
- Which maintained Python FF1 implementation, if any, and its licence and patent position?
- Measured word-list round-trip survival on the target LLMs (needs an experiment).
- PGP word list, proquint and Bubble Babble licences, and the FIPS 181 withdrawal date, need confirmation from primary sources.
- NIST SP 800-57 Part 1 details were not checked.
- Should a Danish name list (and its licence) be bundled, or generated by Faker's `da_DK` locale?

## REFERENCES

1. [EDPB, Guidelines 01/2025 on Pseudonymisation, adopted 16 January 2025, version for public consultation (PDF)](https://www.edpb.europa.eu/system/files/2025-01/edpb_guidelines_202501_pseudonymisation_en.pdf)
2. [NIST SP 800-38G Rev. 1, Second Public Draft (3 Feb 2025)](https://csrc.nist.gov/pubs/sp/800/38/g/r1/2pd)
3. [mysto/python-fpe (PyPI `ff3`), README and licence](https://github.com/mysto/python-fpe)
4. [cryptography on PyPI](https://pypi.org/project/cryptography/)
5. [RFC 5297, Synthetic Initialization Vector (SIV) Authenticated Encryption](https://www.rfc-editor.org/rfc/rfc5297)
6. [Faker on PyPI](https://pypi.org/project/Faker/)
7. [emulbreh/pyffx](https://github.com/emulbreh/pyffx)
8. [mnemonic on PyPI](https://pypi.org/project/mnemonic/)
9. [petname on PyPI](https://pypi.org/project/petname/)
10. [woodruffw/pyrage](https://github.com/woodruffw/pyrage)
11. [argon2-cffi on PyPI](https://pypi.org/project/argon2-cffi/)
12. [keyring on PyPI](https://pypi.org/project/keyring/)
13. [EFF large wordlist](https://www.eff.org/files/2016/07/18/eff_large_wordlist.txt) and [BIP-39 English list](https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt) (sizes counted directly)
