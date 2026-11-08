# nyms.spans

Spans: where a detector found something, and how findings are merged and applied.

A [`Span`](#nyms.spans.Span) is a half-open character interval `[start, end)` over the text as given
(Python `str` indexing, so code points, never bytes or tokens), with the entity type the
detector assigned, the matched text, a confidence score in `[0, 1]` and the detector’s
name. Spans from several detectors overlap, and [`resolve_overlaps()`](#nyms.spans.resolve_overlaps) decides which
survive: the longer span first, then the higher score, then the earlier one. That order is
a function so it can be tested and replaced.

```pycon
>>> a = Span(0, 5, 'PERSON', 'Hans ', 0.5, 'heuristic')
>>> b = Span(0, 11, 'PERSON', 'Hans Jensen', 0.9, 'gazetteer')
>>> [s.detector for s in resolve_overlaps([a, b])]
['gazetteer']
>>> apply_replacements('Hans Jensen bor her', [(b, '[PERSON_1]')])
'[PERSON_1] bor her'
```

### Module Attributes

| [`WEAK_SCORE`](#nyms.spans.WEAK_SCORE)   | it never outranks an overlapping strong span, however long.   |
|---------------------------------------------------------------|---------------------------------------------------------------|

### Functions

| [`apply_replacements`](#nyms.spans.apply_replacements)(text, replacements)   | Rebuild *text* with each span replaced by its string.                                  |
|-------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| [`default_priority`](#nyms.spans.default_priority)(span)                   | Sort key: strong spans before weak ones, then longer, then higher score, then earlier. |
| [`resolve_overlaps`](#nyms.spans.resolve_overlaps)(spans, \*[, priority])  | Keep a non-overlapping subset of *spans*, best first by *priority*, in text order.     |

### Classes

| [`Span`](#nyms.spans.Span)(start, end, entity_type, text[, score, ...])   | One detected occurrence of an entity in a text.   |
|------------------------------------------------------------------------------------------------------|---------------------------------------------------|

### *class* nyms.spans.Span(start, end, entity_type, text, score=1.0, detector='', value=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One detected occurrence of an entity in a text.

#### value *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

a surname mention
(“Jensen”) that stands for a known full name (“Rasmus Jensen”).

* **Type:**
  The value this span stands for when it differs from the text

### nyms.spans.WEAK_SCORE *= 0.6*

it never outranks an overlapping strong span, however long.

* **Type:**
  Below this score a span is “weak”

### nyms.spans.apply_replacements(text, replacements)

Rebuild *text* with each span replaced by its string. Spans must not overlap.

```pycon
>>> apply_replacements('a b c', [(Span(2, 3, 'X', 'b'), 'B')])
'a B c'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### nyms.spans.default_priority(span)

Sort key: strong spans before weak ones, then longer, then higher score, then earlier.

A long, low-confidence heuristic match must not swallow a short, certain one (a gazetteer
name inside a capitalised phrase); among spans of the same strength, the longer wins
(an address over the postcode inside it), then the score (a date over a phone number of
the same length).

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)

### nyms.spans.resolve_overlaps(spans, \*, priority=<function default_priority>)

Keep a non-overlapping subset of *spans*, best first by *priority*, in text order.

```pycon
>>> s = [Span(0, 4, 'A', 'aaaa', 0.5), Span(2, 6, 'B', 'bbbb', 0.9), Span(8, 9, 'C', 'c')]
>>> [x.entity_type for x in resolve_overlaps(s)]
['B', 'C']
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Span`](#nyms.spans.Span)]
