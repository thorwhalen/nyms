# nyms

nyms: reversible pseudonymisation of text before it reaches an AI.

A deterministic (non-AI) pass detects personal and sensitive identifiers in Danish and English
text, replaces them with surrogates from a configurable strategy, remembers the mapping per
project so the same person is the same pseudonym in every document, and puts the originals
back into whatever the AI answers.

```pycon
>>> from nyms import Pseudonymiser
>>> p = Pseudonymiser(store={})
>>> p.pseudonymise("Mail hans.jensen@example.dk, tlf. 12 34 56 78").text
'Mail [EMAIL_1], tlf. [PHONE_1]'
```

### Functions

| [`default_detectors`](#nyms.default_detectors)(\*[, names, languages])      | The deterministic detector set.                                                                                       |
|-------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| [`detect`](#nyms.detect)(text[, detectors])                      | Run *detectors* (default: [`default_detectors()`](#nyms.default_detectors)) and resolve overlaps. |
| [`gazetteer_detector`](#nyms.gazetteer_detector)(names, \*[, name, ...])     | A detector for a list of known names (full names or first names), case-insensitive.                                   |
| [`known_values_detectors`](#nyms.known_values_detectors)(records, \*[, ...])     | Detectors for what a project already knows: its values, their name components, its surrogates.                        |
| [`local_mapping_store`](#nyms.local_mapping_store)([project, rootdir, codec]) | A `dol` file store of records under the project dir, optionally through *codec*.                                      |
| [`normalise`](#nyms.normalise)(entity_type, text)                   | The identity of a value for the purpose of "same surrogate".                                                          |
| [`apply_replacements`](#nyms.apply_replacements)(text, replacements)         | Rebuild *text* with each span replaced by its string.                                                                 |
| [`resolve_overlaps`](#nyms.resolve_overlaps)(spans, \*[, priority])        | Keep a non-overlapping subset of *spans*, best first by *priority*, in text order.                                    |
| [`readable`](#nyms.readable)(value, \*, key[, entity_type, ...])   | The stand-alone tool: a keyed hash of *value*, as readable words.                                                     |
| [`words_from_bytes`](#nyms.words_from_bytes)(data, \*[, n, wordlist])      | Render *data* as *n* words from *wordlist* (default: the EFF short list).                                             |

### Classes

| [`Pseudonymiser`](#nyms.Pseudonymiser)([project, detectors, ...])          | The facade.                                                                           |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| [`Reidentified`](#nyms.Reidentified)(text, restored, unmatched)           | What `Pseudonymiser.reidentify()` returns.                                            |
| [`Result`](#nyms.Result)(text, replaced, kept, replacements[, ...]) | What `Pseudonymiser.pseudonymise()` returns.                                          |
| [`Detector`](#nyms.Detector)(name, entity_type, pattern[, ...])       | A regex detector with an optional validator and context words.                        |
| [`DetectorLike`](#nyms.DetectorLike)(\*args, \*\*kwargs)                  | Anything that turns text into spans.                                                  |
| [`MappingStore`](#nyms.MappingStore)([store, strategy])                   | Records keyed by surrogate, with an in-memory index by `(entity_type, normalised)`.   |
| [`Policy`](#nyms.Policy)([name, include, exclude, min_score, ...])  | What to do with detected spans.                                                       |
| [`Span`](#nyms.Span)(start, end, entity_type, text[, score, ...]) | One detected occurrence of an entity in a text.                                       |
| [`Aliases`](#nyms.Aliases)(aliases[, fallback])                      | The user's own surrogates for some values; *fallback* for the rest.                   |
| [`Counter`](#nyms.Counter)([template])                               | `[PERSON_1]`-style typed counters, numbered per entity type within the project.       |
| [`KeyedWords`](#nyms.KeyedWords)(key[, n_words, wordlist, ...])         | Keyed hash (HMAC-SHA-256) rendered as readable words.                                 |
| [`RandomWords`](#nyms.RandomWords)([n_words, wordlist, templates, ...])  | Random readable words (a tokenisation vault): no key, no information about the value. |
| [`EntityType`](#nyms.EntityType)(name, identifier_class, tier[, ...])   | One entity type and its place in the taxonomy.                                        |

### *class* nyms.Aliases(aliases, fallback=Counter())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The user’s own surrogates for some values; *fallback* for the rest.

Keys are compared casefolded and whitespace-collapsed.

```pycon
>>> a = Aliases({'Hans Jensen': 'Mr Green'}, fallback=Counter())
>>> a('PERSON', 'hans  jensen', vault=_EmptyVault()), a('PERSON', 'Else Berg', vault=_EmptyVault())
('Mr Green', '[PERSON_1]')
```

### *class* nyms.Counter(template='[{type}_{n}]')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

`[PERSON_1]`-style typed counters, numbered per entity type within the project.

### *class* nyms.Detector(name, entity_type, pattern, score=1.0, validate=None, group=0, context=tuple(), value_of=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A regex detector with an optional validator and context words.

`validate(match)` may return `False` (drop), `True`/`None` (keep the base
score) or a float (use it as the score). `group` picks the capture group that is
the span (the whole match by default). `value_of(match)` may name the canonical value
the span stands for when it differs from the matched text.

### *class* nyms.DetectorLike(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Anything that turns text into spans. `name` and `entity_type` are optional.

### *class* nyms.EntityType(name, identifier_class, tier, description='', aliases=tuple())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One entity type and its place in the taxonomy.

### *class* nyms.KeyedWords(key, n_words=2, wordlist=None, templates=<factory>, default_template='[{type}:{words}]')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Keyed hash (HMAC-SHA-256) rendered as readable words. Deterministic under one key.

### *class* nyms.MappingStore(store=None, , strategy=None)

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

### *class* nyms.Policy(name='default', include=None, exclude=frozenset({}), min_score=0.5, min_score_by_type=dict(), allow=frozenset({}), deny=frozenset({}), keep=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What to do with detected spans. See the module docstring.

#### accepts(span)

Whether *span* gets replaced under this policy (post-detection decision).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### detector_filter(detectors)

The detectors whose entity type this policy wants; a pre-detection filter.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

#### split(spans)

`(replaced, kept)` under this policy.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Span`](nyms.spans.html.md#nyms.spans.Span)], [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Span`](nyms.spans.html.md#nyms.spans.Span)]]

#### wants(entity_type)

Whether this policy acts on a type at all (pre-detection filter).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

#### with_names(\*names)

A copy whose deny list also holds *names* (casefolded): the parties you know.

```pycon
>>> p = Policy.default().with_names('Acme ApS')
>>> 'acme aps' in p.deny
True
```

* **Return type:**
  [`Policy`](nyms.policy.html.md#nyms.policy.Policy)

### *class* nyms.Pseudonymiser(project='default', , detectors=None, post_detectors=(), policy=None, strategy=None, store=None, key=None, names=(), rootdir=None, encrypt=False, prefilter=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The facade. See the module docstring for the seams.

#### check(text)

Originals from the mapping that occur in *text*: what would leak if it were sent.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### *class* nyms.RandomWords(n_words=2, wordlist=None, templates=<factory>, default_template='[{type}:{words}]')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Random readable words (a tokenisation vault): no key, no information about the value.

### *class* nyms.Reidentified(text, restored, unmatched)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What `Pseudonymiser.reidentify()` returns.

### *class* nyms.Result(text, replaced, kept, replacements, report=dict(), post_replacements=list())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What `Pseudonymiser.pseudonymise()` returns. Spans refer to the NFC-normalised input.

#### *property* mapping *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

`{surrogate: original}` for this run only. Sensitive.

#### post_replacements *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Span](nyms.spans.html.md#nyms.spans.Span), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]*

Stage-2 replacements (`post_detectors`), with offsets in the stage-1 output.

### *class* nyms.Span(start, end, entity_type, text, score=1.0, detector='', value=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One detected occurrence of an entity in a text.

#### value *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

a surname mention
(“Jensen”) that stands for a known full name (“Rasmus Jensen”).

* **Type:**
  The value this span stands for when it differs from the text

### nyms.apply_replacements(text, replacements)

Rebuild *text* with each span replaced by its string. Spans must not overlap.

```pycon
>>> apply_replacements('a b c', [(Span(2, 3, 'X', 'b'), 'B')])
'a B c'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### nyms.default_detectors(, names=(), languages=('da', 'en'))

The deterministic detector set. *names* are the parties you already know.

Order does not matter for the result (overlaps are resolved afterwards), only for the
report’s grouping.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Detector`](#nyms.Detector)]

### nyms.detect(text, detectors=None)

Run *detectors* (default: [`default_detectors()`](#nyms.default_detectors)) and resolve overlaps.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Span`](nyms.spans.html.md#nyms.spans.Span)]

### nyms.gazetteer_detector(names, , name='gazetteer', entity_type='PERSON', score=1.0, surname_tail=True, value_of_name=None, single_word_score=0.85)

A detector for a list of known names (full names or first names), case-insensitive.

A first name followed by capitalised words extends to the full name when *surname_tail*
is true. A genitive `s` on the last word stays in the span; the mapping store decides
whether it is a genitive of a known value. *value_of_name* may map the matched text to the
canonical value it stands for (a surname to the full name).

```pycon
>>> d = gazetteer_detector(['Rasmus'])
>>> [s.text for s in d('Rasmus Jensens bil, og Rasmus selv.')]
['Rasmus Jensens', 'Rasmus']
```

* **Return type:**
  [`Detector`](#nyms.Detector)

### nyms.known_values_detectors(records, , extra_names=(), score=1.0)

Detectors for what a project already knows: its values, their name components, its surrogates.

- every original in the mapping, by type: names through [`gazetteer_detector()`](#nyms.gazetteer_detector) (word
  boundaries, genitive), everything else literally;
- for persons, each component (first name or surname) that identifies exactly one known
  person, standing for the full name (`Span.value`), scored above a lone first name from
  the bundled list so the known person wins;
- every surrogate already issued, as `SURROGATE_TYPE`, so the project’s own
  surrogates are never re-detected as names when pseudonymised text is processed again.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Detector`](#nyms.Detector)]

### nyms.local_mapping_store(project='default', , rootdir=None, codec=None)

A `dol` file store of records under the project dir, optionally through *codec*.

*codec* is a pair `(encode: bytes -> bytes, decode: bytes -> bytes)` applied to the JSON
bytes of each record; see `encrypted()`. The project’s `meta.json` records which
codec the store was created with; a mismatch raises `StoreError`.

* **Return type:**
  [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### nyms.normalise(entity_type, text)

The identity of a value for the purpose of “same surrogate”.

```pycon
>>> normalise('CPR', '010190-1234'), normalise('PERSON', ' Hans   JENSEN '), normalise('EMAIL', 'A@B.dk')
('0101901234', 'hans jensen', 'a@b.dk')
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### nyms.readable(value, , key, entity_type='VALUE', n_words=2, wordlist=None)

The stand-alone tool: a keyed hash of *value*, as readable words.

```pycon
>>> readable('010190-1234', key=b'0' * 32) == readable('010190-1234', key=b'0' * 32)
True
>>> readable('010190-1234', key=b'0' * 32) != readable('010190-1234', key=b'1' * 32)
True
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### nyms.resolve_overlaps(spans, \*, priority=<function default_priority>)

Keep a non-overlapping subset of *spans*, best first by *priority*, in text order.

```pycon
>>> s = [Span(0, 4, 'A', 'aaaa', 0.5), Span(2, 6, 'B', 'bbbb', 0.9), Span(8, 9, 'C', 'c')]
>>> [x.entity_type for x in resolve_overlaps(s)]
['B', 'C']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Span`](nyms.spans.html.md#nyms.spans.Span)]

### nyms.words_from_bytes(data, , n=2, wordlist=None)

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

### Modules

| [`core`](nyms.core.html.md#module-nyms.core)             | The facade: detect, pseudonymise, re-identify, check.                                   |
|------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| [`data`](nyms.data.html.md#module-nyms.data)             | Bundled data files (data), shipped inside the wheel.                                    |
| [`keys`](nyms.keys.html.md#module-nyms.keys)             | Key management for a single user or a small team: where the project's secret lives.     |
| [`mapping`](nyms.mapping.html.md#module-nyms.mapping)       | The reversible mapping store: surrogate <-> original, per project, on a `dol` store.    |
| [`policy`](nyms.policy.html.md#module-nyms.policy)         | The sensitivity policy: which detected spans get replaced, which are kept and reported. |
| [`spans`](nyms.spans.html.md#module-nyms.spans)           | Spans: where a detector found something, and how findings are merged and applied.       |
| [`surrogates`](nyms.surrogates.html.md#module-nyms.surrogates) | Surrogate (pseudonym) generation: what replaces a detected value.                       |
| [`taxonomy`](nyms.taxonomy.html.md#module-nyms.taxonomy)     | The entity taxonomy: what kinds of things nyms detects, and how sensitive each is.      |
| [`tools`](nyms.tools.html.md#module-nyms.tools)           | The SSOT of operations: plain functions, JSON-able in and out, surface-agnostic.        |
