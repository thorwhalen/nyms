# nyms.tools

The SSOT of operations: plain functions, JSON-able in and out, surface-agnostic.

The CLI (`nyms.__main__`, via `cw`) dispatches this module’s `_dispatch_funcs`; an MCP
server (`py2mcp.mk_mcp_from_refs(['nyms.tools:pseudonymise', ...])`) or an HTTP adapter would
reference the same names. Nothing here prints or exits; nothing imports a surface.

Every verb takes the content as positional `text` or, exclusively, a `path` (a UTF-8 file,
or `-` for stdin). The two are never guessed from each other: a value that happens to be an
existing path is still text. The project key is touched only when a verb needs it.

### Functions

| [`check`](#nyms.tools.check)([text, path, project, encrypt])            | Originals of *project* that occur in the text: what would leak if this text were sent.                                  |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------|
| [`detect`](#nyms.tools.detect)([text, path, names, policy])              | The spans the deterministic pass finds, with the policy's decision for each.                                            |
| [`mapping`](#nyms.tools.mapping)([project, encrypt])                      | The project's records (surrogate, original, type).                                                                      |
| [`policies`](#nyms.tools.policies)()                                       | The policy presets and the entity types each replaces.                                                                  |
| [`pseudonymise`](#nyms.tools.pseudonymise)([text, path, project, out, ...])    | Replace detected identifiers in the text (or the file at *path*) with surrogates; the project's mapping remembers them. |
| [`readable`](#nyms.tools.readable)(value, \*[, project, entity_type, ...]) | A keyed hash of *value* under the project's key, rendered as readable words.                                            |
| [`reidentify`](#nyms.tools.reidentify)([text, path, project, out, encrypt])  | Put the originals back into the text (an AI's answer, say).                                                             |

### nyms.tools.check(text='', , path='', project='default', encrypt=False)

Originals of *project* that occur in the text: what would leak if this text were sent.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### nyms.tools.detect(text='', , path='', names='', policy='default')

The spans the deterministic pass finds, with the policy’s decision for each. Nothing is stored.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### nyms.tools.mapping(project='default', , encrypt=False)

The project’s records (surrogate, original, type). Sensitive: this is the key to the text.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]

### nyms.tools.policies()

The policy presets and the entity types each replaces.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### nyms.tools.pseudonymise(text='', , path='', project='default', out=None, policy='default', names='', strategy='counter', aliases='', encrypt=False)

Replace detected identifiers in the text (or the file at *path*) with surrogates; the project’s mapping remembers them.

*names*: comma-separated names you already know (the parties). *aliases*: `Name=Alias,...`
surrogates you choose yourself. *strategy*: `counter` (`[PERSON_1]`), `keyed-words`
or `random-words`. The result carries the text (or the `out` path) and the run report.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### nyms.tools.readable(value, , project='default', entity_type='VALUE', n_words=2)

A keyed hash of *value* under the project’s key, rendered as readable words.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### nyms.tools.reidentify(text='', , path='', project='default', out=None, encrypt=False)

Put the originals back into the text (an AI’s answer, say). Lists tokens it could not place.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)
