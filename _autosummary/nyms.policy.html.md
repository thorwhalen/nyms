# nyms.policy

The sensitivity policy: which detected spans get replaced, which are kept and reported.

A [`Policy`](#nyms.policy.Policy) is evaluated **after** detection (all detectors run, the policy decides),
which is what lets the run report say what it saw and chose to keep. A policy can also be
applied **before** detection through [`Policy.detector_filter()`](#nyms.policy.Policy.detector_filter), to skip detectors whose
type it will never act on; both orders are supported because the user asked for both.

Three presets:

- `Policy.default()`: tiers 0 and 1, plus organisation identifiers and amounts; dates,
  postcodes and URLs are kept and reported.
- `Policy.identifiers()`: tiers 0 and 1 only.
- `Policy.strict()`: everything detected.

Allow and deny lists are matched on the span text, case-insensitively: `allow` is never
replaced (a public institution’s name, say), `deny` is always replaced (the parties’
names, which no detector may know). A policy is a plain dataclass, so it serialises to and
from a dict (`to_dict()`, `from_dict()`) and can live in a project file.

```pycon
>>> from nyms.spans import Span
>>> p = Policy.default()
>>> p.accepts(Span(0, 10, 'CPR', '010190-1234', 0.9))
True
>>> p.accepts(Span(0, 10, 'DATE', '01.01.1990', 0.9))
False
>>> Policy.strict().accepts(Span(0, 10, 'DATE', '01.01.1990', 0.9))
True
```

### Classes

| [`Policy`](#nyms.policy.Policy)([name, include, exclude, min_score, ...])   | What to do with detected spans.   |
|-----------------------------------------------------------------------------------------------------|-----------------------------------|

### *class* nyms.policy.Policy(name='default', include=None, exclude=frozenset({}), min_score=0.5, min_score_by_type=dict(), allow=frozenset({}), deny=frozenset({}), keep=None)

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
  [`Policy`](#nyms.policy.Policy)
