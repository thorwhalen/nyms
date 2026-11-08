# ADR 0005: the reversible mapping store and key management

*2026-11-08 · status: accepted · research: [surrogates-crypto-and-keys](../research/surrogates-crypto-and-keys.md) §3 and §4, [pipeline-architecture-and-agent-practice](../research/pipeline-architecture-and-agent-practice.md) §2*

## Context

The mapping (surrogate to original) and the key are the "additional information" of GDPR Art. 4(5): whoever holds them re-identifies everything. Every LLM privacy gateway surveyed keeps such a store and warns that it is sensitive; Presidio keeps none and so cannot be consistent across documents. The in-house storage facade is `dol`; the in-house secret resolution is `config2py`; `cryptography` is installed but is not a dependency of a minimal package.

## Decision

- **Store** (`nyms.mapping.MappingStore`): one record per distinct value (surrogate, original, entity type, normalised form, strategy, time), keyed by surrogate, indexed in memory by `(entity_type, normalised)`. Normalisation decides identity: digits only for numeric identifiers, upper-case alphanumerics for IBAN and case numbers, lower case for e-mail and URL, casefolded and whitespace-collapsed for the rest.
- **Backing store**: any `MutableMapping[str, dict]`. Default `local_mapping_store(project)`: `dol.JsonFiles` under `~/.local/share/nyms/<project>/mapping/` (XDG-aware), one JSON file per record, directory mode 0700. A `dict` is the in-memory store for tests and one-off runs. The repository never holds a store; the default root is outside any project directory by design.
- **Encryption at rest is a seam** (`codec=`): `encrypted(key)` gives a Fernet codec (AES-128-CBC with HMAC-SHA-256) from the optional `cryptography` dependency (`pip install "nyms[crypto]"`, `encrypt=True` on the facade). The default is plaintext in the user's data directory because the standard library has no authenticated cipher and a default must not need a new dependency. The trade-off is stated in the README.
- **Key** (`nyms.keys.resolve_key`): the `NYMS_KEY` environment variable (hex or base64), then a per-project key file under `~/.config/nyms/keys/<project>.key` (32 random bytes, mode 0600, created on first use), then, when a passphrase is given, scrypt derivation with a stored per-project salt. The key file and the mapping directory are never in the same tree. Replacements: `keyring` (OS keychain), `config2py`, `age`, a KMS, each one `key=` argument.
- **Rotation** is a new project. Keyed-word surrogates change with the key by construction; counter surrogates survive it because they live in the store. Re-keying an encrypted store means decrypting and re-encrypting the records.
- **Loss**: lose the store and counter surrogates cannot be reversed; lose the key and an encrypted store cannot be read and keyed-word surrogates cannot be regenerated. Both are stated in the README; a backup is the user's job.
- `MappingStore.to_dict()` and the `nyms mapping` command print originals. They exist because the user owns the data; the docs mark them sensitive.

## Alternatives considered

- Append-only log with compaction: more robust for concurrent writers, more code. One file per record on `dol` gives inspectability and `dol`'s backends for free; deferred.
- OS keyring as the default key store: the right replacement, but a new dependency and an interactive prompt on first use. Not the default.
- Per-document keys: destroys cross-document consistency, which is the point of a project. Rejected.

## Consequences

A project is the unit of consistency, of key and of store. Two sessions on one project write to the same directory; `dol.JsonFiles` writes are per record, so interleaving is safe at record granularity but the in-memory counter can issue a duplicate under true concurrency. Not a v1 concern; noted for the store seam.
