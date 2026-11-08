# nyms.mapping

The reversible mapping store: surrogate <-> original, per project, on a `dol` store.

A [`MappingStore`](#nyms.mapping.MappingStore) holds one [`Record`](#nyms.mapping.Record) per distinct value: entity type, original,
normalised form, surrogate, aliases (other normalised forms that stand for the same value,
such as a surname alone), strategy name and creation time. It is keyed by surrogate (so
re-identification is one lookup) and indexes every normalised form in memory so the same
value gets the same surrogate on every occurrence and in every document of the project.

The backing store is any `MutableMapping[str, dict]`. The default,
[`local_mapping_store()`](#nyms.mapping.local_mapping_store), is `dol.JsonFiles` under `~/.local/share/nyms/<project>/mapping`,
one JSON file per record (file names are a URL-safe encoding of the surrogate, so any
surrogate string is a legal file name on any platform), which a human can inspect and
delete. Encryption at rest is the `codec` seam: pass [`encrypted()`](#nyms.mapping.encrypted) (needs the optional
`cryptography` dependency) and every value is Fernet-encrypted under the project key before
it hits disk. The project directory carries a `meta.json` naming the codec, so opening an
encrypted store without the codec (or the reverse) fails with a clear message.

Normalisation decides what counts as “the same value”: digits only for numeric identifiers,
casefolded and whitespace-collapsed for names, lower case for e-mail. The Danish genitive is
handled in [`MappingStore.resolve()`](#nyms.mapping.MappingStore.resolve): `Rasmus Jensens` resolves to `Rasmus Jensen`’s
surrogate plus the suffix `s` when that person is already known, and the facade writes
`[PERSON_1]s`. A first-seen `...s` is taken literally; if the base form turns up later,
the record is relinked to it.

```pycon
>>> from nyms.surrogates import Counter
>>> m = MappingStore({}, strategy=Counter())
>>> m.resolve('PERSON', 'Rasmus Jensen')
('[PERSON_1]', '')
>>> m.resolve('PERSON', 'Rasmus Jensens')
('[PERSON_1]', 's')
>>> m.resolve('CPR', '010190 1234') == m.resolve('CPR', '010190-1234')
True
>>> m.original('[PERSON_1]')
'Rasmus Jensen'
```

### Functions

| [`canon`](#nyms.mapping.canon)(surrogate)                               | The loose form of a surrogate used for re-identification and collision checks.   |
|-------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| [`encrypted`](#nyms.mapping.encrypted)(key)                                 | A `(encode, decode)` codec: Fernet under a key derived from *key*.               |
| [`local_mapping_store`](#nyms.mapping.local_mapping_store)([project, rootdir, codec]) | A `dol` file store of records under the project dir, optionally through *codec*. |
| [`normalise`](#nyms.mapping.normalise)(entity_type, text)                   | The identity of a value for the purpose of "same surrogate".                     |
| [`project_dir`](#nyms.mapping.project_dir)(project, \*[, rootdir])            | Where a project's data lives: `<rootdir or ~/.local/share/nyms>/<project>`.      |

### Classes

| [`MappingStore`](#nyms.mapping.MappingStore)([store, strategy])               | Records keyed by surrogate, with an in-memory index by `(entity_type, normalised)`.   |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| [`Record`](#nyms.mapping.Record)(surrogate, original, entity_type, ...) | One distinct value and its surrogate.                                                 |

### Exceptions

| [`StoreError`](#nyms.mapping.StoreError)   | A mapping store could not be opened the way it was created (codec mismatch).   |
|---------------------------------------------------------------|--------------------------------------------------------------------------------|

### *class* nyms.mapping.MappingStore(store=None, , strategy=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Records keyed by surrogate, with an in-memory index by `(entity_type, normalised)`.

#### add(entity_type, text, , surrogate=None)

Create a record for a new value (with a given *surrogate*, or one from the strategy).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### add_alias_form(surrogate, entity_type, text)

Make *text* (a surname alone, say) resolve to an existing record’s surrogate.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

#### alias(entity_type, text, surrogate)

Choose the surrogate for a value yourself (before it is first seen).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### resolve(entity_type, text)

`(surrogate, suffix)` for *text*, creating the surrogate if the value is new.

*suffix* is a genitive ending found on an already known value, to be re-attached
after the surrogate (`[PERSON_1]` + `s`). It is empty for a new value: nyms does
not guess that an unknown `...s` is a genitive; if the base form appears later the
record is relinked to it.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### to_dict()

`{surrogate: original}`. This is the sensitive artefact; handle it as such.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### *class* nyms.mapping.Record(surrogate, original, entity_type, normalised, strategy='', created=0.0, aliases=tuple())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One distinct value and its surrogate.

### *exception* nyms.mapping.StoreError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

A mapping store could not be opened the way it was created (codec mismatch).

### nyms.mapping.canon(surrogate)

The loose form of a surrogate used for re-identification and collision checks.

```pycon
>>> canon('[ PERSON 1 ]'), canon('Alder  Brook')
('person_1', 'alder_brook')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### nyms.mapping.encrypted(key)

A `(encode, decode)` codec: Fernet under a key derived from *key*. Needs `cryptography`.

Fernet (AES-128-CBC with HMAC-SHA-256) is the simplest authenticated encryption the
`cryptography` package offers; AES-GCM or `age` are the replacements.

### nyms.mapping.local_mapping_store(project='default', , rootdir=None, codec=None)

A `dol` file store of records under the project dir, optionally through *codec*.

*codec* is a pair `(encode: bytes -> bytes, decode: bytes -> bytes)` applied to the JSON
bytes of each record; see [`encrypted()`](#nyms.mapping.encrypted). The project’s `meta.json` records which
codec the store was created with; a mismatch raises [`StoreError`](#nyms.mapping.StoreError).

* **Return type:**
  [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### nyms.mapping.normalise(entity_type, text)

The identity of a value for the purpose of “same surrogate”.

```pycon
>>> normalise('CPR', '010190-1234'), normalise('PERSON', ' Hans   JENSEN '), normalise('EMAIL', 'A@B.dk')
('0101901234', 'hans jensen', 'a@b.dk')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### nyms.mapping.project_dir(project, , rootdir=None)

Where a project’s data lives: `<rootdir or ~/.local/share/nyms>/<project>`.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
