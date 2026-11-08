# nyms.core

The facade: detect, pseudonymise, re-identify, check. One object, six seams.

```default
from nyms import Pseudonymiser
p = Pseudonymiser('case-2026', names=['Rasmus Jensen'])
result = p.pseudonymise(text)      # result.text goes to the AI; result.report says what happened
answer = p.reidentify(ai_output)   # answer.text has the originals back; answer.unmatched lists invented tokens
p.check(outgoing_text)             # originals that would leak, before anything is sent
```

The seams, each one keyword argument of [`Pseudonymiser`](#nyms.core.Pseudonymiser):

Not seams, written directly on purpose: the span data model, the report’s shape, the
tolerant re-identification matcher, the order of the stages.

How a run works. The text is NFC-normalised. Stage 1: every detector’s spans, overlap
resolution (strong spans before weak, longer before shorter), the policy’s split into
replaced and kept; an accepted span nested inside a kept one (a CPR number inside a URL the
policy keeps) is still replaced. New values enter the mapping, and a second pass adds
detectors for everything the project knows (its values, name components, its own surrogates)
so every occurrence is consistent. Stage 2, when `post_detectors` are given: they run on the
pseudonymised text, where the surrogates are protected from re-detection, and what they find
is replaced and added to the mapping too.

```pycon
>>> p = Pseudonymiser(store={})
>>> r = p.pseudonymise("Rasmus Jensen (CPR 010190-1234) skylder 12.500 kr. Rasmus Jensens advokat ringede.")
>>> r.text
'[PERSON_1] (CPR [CPR_1]) skylder [AMOUNT_1]. [PERSON_1]s advokat ringede.'
>>> p.reidentify("Svar: [PERSON_1] skal betale [AMOUNT_1]. [person 1]s sag.").text
'Svar: Rasmus Jensen skal betale 12.500 kr. Rasmus Jensens sag.'
>>> p.check("Rasmus Jensen bor her")
['Rasmus Jensen']
>>> p.pseudonymise(r.text).text == r.text   # idempotent: surrogates are never re-detected
True
```

### Module Attributes

| [`PROMOTABLE_TYPES`](#nyms.core.PROMOTABLE_TYPES)   | structured identifiers, whose match is unambiguous.   |
|---------------------------------------------------------------------|-------------------------------------------------------|

### Classes

| [`Pseudonymiser`](#nyms.core.Pseudonymiser)([project, detectors, ...])          | The facade.                                  |
|----------------------------------------------------------------------------------------------------|----------------------------------------------|
| [`Reidentified`](#nyms.core.Reidentified)(text, restored, unmatched)           | What `Pseudonymiser.reidentify()` returns.   |
| [`Result`](#nyms.core.Result)(text, replaced, kept, replacements[, ...]) | What `Pseudonymiser.pseudonymise()` returns. |

### nyms.core.PROMOTABLE_TYPES *= frozenset({'BANK_ACCOUNT', 'CASE_ID', 'CPR', 'CREDENTIAL', 'CVR', 'EMAIL', 'IBAN', 'PHONE'})*

structured identifiers, whose match is
unambiguous. Names are not (a first name inside a kept date: “1. Maj 2024”).

* **Type:**
  Entity types promoted out of a kept container span

### *class* nyms.core.Pseudonymiser(project='default', , detectors=None, post_detectors=(), policy=None, strategy=None, store=None, key=None, names=(), rootdir=None, encrypt=False, prefilter=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The facade. See the module docstring for the seams.

#### check(text)

Originals from the mapping that occur in *text*: what would leak if it were sent.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### *class* nyms.core.Reidentified(text, restored, unmatched)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What `Pseudonymiser.reidentify()` returns.

### *class* nyms.core.Result(text, replaced, kept, replacements, report=dict(), post_replacements=list())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What `Pseudonymiser.pseudonymise()` returns. Spans refer to the NFC-normalised input.

#### *property* mapping *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

`{surrogate: original}` for this run only. Sensitive.

#### post_replacements *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Span](nyms.spans.html.md#nyms.spans.Span), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]*

Stage-2 replacements (`post_detectors`), with offsets in the stage-1 output.
