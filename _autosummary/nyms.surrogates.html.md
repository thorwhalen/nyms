# nyms.surrogates

Surrogate (pseudonym) generation: what replaces a detected value.

A **surrogate strategy** is a callable `(entity_type, value, *, vault) -> str` that returns
the replacement for a value seen for the first time; the mapping store calls it once per new
value and remembers the answer, so every later occurrence gets the same surrogate. `vault`
is the store itself, exposing `__contains__` (is this surrogate taken?) and
`count(entity_type)`, which is all a strategy needs to avoid collisions or number things.

Four strategies, matching the surrogate research (`docs/research/surrogates-crypto-and-keys.md`):

- [`Counter`](#nyms.surrogates.Counter): `[PERSON_1]`, `[CPR_2]`. The default. Bracketed typed tokens were
  the form LLMs altered least in the one benchmark found, and the counter is per project
  (persisted with the store), so the same person is `[PERSON_1]` in every document.
- [`KeyedWords`](#nyms.surrogates.KeyedWords): HMAC-SHA-256 of the value under a secret key, rendered as readable
  words from a word list (`[PERSON:alder-brook]`, or name-shaped `Alder Brook`). The
  same key gives the same surrogate on any machine without sharing a store, which is the
  property the vault lacks. Never unkeyed: a plain hash of a CPR number falls to enumeration.
- [`RandomWords`](#nyms.surrogates.RandomWords): readable words from random bytes. A classic tokenisation vault.
- [`Aliases`](#nyms.surrogates.Aliases): the user’s own choice for some values (“call the landlord Mr Green”),
  with any other strategy as the fallback.

The rendering of bytes to words ([`words_from_bytes()`](#nyms.surrogates.words_from_bytes)) is separate from where the bytes
come from, and is the tool the user asked for (“a cryptographic hash mapped to a sequence of
letters that is actually readable”). It also stands alone:

```pycon
>>> words_from_bytes(b'\x00' * 8, n=2)
['aardvark', 'aardvark']
>>> Counter()('PERSON', 'Hans Jensen', vault=_EmptyVault())
'[PERSON_1]'
>>> KeyedWords(b'k' * 32)('CPR', '010190-1234', vault=_EmptyVault())
'[CPR:...]'
```

### Module Attributes

| [`DEFAULT_WORD_TEMPLATES`](#nyms.surrogates.DEFAULT_WORD_TEMPLATES)   | Templates per entity type for word surrogates.   |
|---------------------------------------------------------------------------|--------------------------------------------------|

### Functions

| [`default_wordlist`](#nyms.surrogates.default_wordlist)()                           | The bundled EFF short wordlist 2.0: 1,296 common words with unique 3-letter prefixes.   |
|-----------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| [`keyed_digest`](#nyms.surrogates.keyed_digest)(key, entity_type, value)        | HMAC-SHA-256 of `entity_type || NUL || value` under *key*.                              |
| [`readable`](#nyms.surrogates.readable)(value, \*, key[, entity_type, ...]) | The stand-alone tool: a keyed hash of *value*, as readable words.                       |
| [`syllables_from_bytes`](#nyms.surrogates.syllables_from_bytes)(data, \*[, n])          | Render *data* as a pronounceable made-up word of *n* consonant-vowel syllables.         |
| [`words_from_bytes`](#nyms.surrogates.words_from_bytes)(data, \*[, n, wordlist])    | Render *data* as *n* words from *wordlist* (default: the EFF short list).               |

### Classes

| [`Aliases`](#nyms.surrogates.Aliases)(aliases[, fallback])                     | The user's own surrogates for some values; *fallback* for the rest.                   |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| [`Counter`](#nyms.surrogates.Counter)([template])                              | `[PERSON_1]`-style typed counters, numbered per entity type within the project.       |
| [`KeyedWords`](#nyms.surrogates.KeyedWords)(key[, n_words, wordlist, ...])        | Keyed hash (HMAC-SHA-256) rendered as readable words.                                 |
| [`RandomWords`](#nyms.surrogates.RandomWords)([n_words, wordlist, templates, ...]) | Random readable words (a tokenisation vault): no key, no information about the value. |
| [`Vault`](#nyms.surrogates.Vault)(\*args, \*\*kwargs)                        | What a strategy may ask of the mapping store.                                         |

### *class* nyms.surrogates.Aliases(aliases, fallback=Counter())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The user’s own surrogates for some values; *fallback* for the rest.

Keys are compared casefolded and whitespace-collapsed.

```pycon
>>> a = Aliases({'Hans Jensen': 'Mr Green'}, fallback=Counter())
>>> a('PERSON', 'hans  jensen', vault=_EmptyVault()), a('PERSON', 'Else Berg', vault=_EmptyVault())
('Mr Green', '[PERSON_1]')
```

### *class* nyms.surrogates.Counter(template='[{type}_{n}]')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`[PERSON_1]`-style typed counters, numbered per entity type within the project.

### nyms.surrogates.DEFAULT_WORD_TEMPLATES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'ORG': '{Words}', 'PERSON': '{Words}'}*

Templates per entity type for word surrogates. `{words}` is hyphen-joined lower case,
`{Words}` is capitalised and space-joined (name-shaped), `{type}` the entity type.

### *class* nyms.surrogates.KeyedWords(key, n_words=2, wordlist=None, templates=<factory>, default_template='[{type}:{words}]')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Keyed hash (HMAC-SHA-256) rendered as readable words. Deterministic under one key.

### *class* nyms.surrogates.RandomWords(n_words=2, wordlist=None, templates=<factory>, default_template='[{type}:{words}]')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Random readable words (a tokenisation vault): no key, no information about the value.

### *class* nyms.surrogates.Vault(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

What a strategy may ask of the mapping store.

### nyms.surrogates.default_wordlist()

The bundled EFF short wordlist 2.0: 1,296 common words with unique 3-letter prefixes.

```pycon
>>> len(default_wordlist())
1296
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]

### nyms.surrogates.keyed_digest(key, entity_type, value)

HMAC-SHA-256 of `entity_type || NUL || value` under *key*.

The type is part of the message so a person and a company with the same string get
different surrogates. The key must be secret: with a public key this is an unkeyed hash
and a low-entropy identifier (a CPR number, a phone number) is recovered by enumeration.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### nyms.surrogates.readable(value, , key, entity_type='VALUE', n_words=2, wordlist=None)

The stand-alone tool: a keyed hash of *value*, as readable words.

```pycon
>>> readable('010190-1234', key=b'0' * 32) == readable('010190-1234', key=b'0' * 32)
True
>>> readable('010190-1234', key=b'0' * 32) != readable('010190-1234', key=b'1' * 32)
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### nyms.surrogates.syllables_from_bytes(data, , n=3)

Render *data* as a pronounceable made-up word of *n* consonant-vowel syllables.

Needs no word list and never collides with a dictionary word, at the cost of looking
invented. 70 syllables, about 6.1 bits each.

```pycon
>>> syllables_from_bytes(b'\x00\x00\x00', n=3)
'bababa'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### nyms.surrogates.words_from_bytes(data, , n=2, wordlist=None)

Render *data* as *n* words from *wordlist* (default: the EFF short list).

The integer value of the bytes is written in base `len(wordlist)`; the lowest *n*
digits become words. Each word of the default list carries log2(1296) = 10.3 bits, so
two words identify about 1.7 million values and three about 2.2 billion.

```pycon
>>> words_from_bytes(bytes([0, 0, 0, 1]), n=2)
['aardvark', 'abandoned']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
