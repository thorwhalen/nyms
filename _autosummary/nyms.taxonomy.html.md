# nyms.taxonomy

The entity taxonomy: what kinds of things nyms detects, and how sensitive each is.

Three axes, following the terminology research (`docs/research/terminology-and-regulation.md`):
the **identifier class** (credential, direct identifier, quasi-identifier, sensitive attribute,
organisation identifier), a **tier** that says what the default policy does with it, and
**aliases** that map the type onto the names Presidio, Google DLP and HIPAA use, so a reader
coming from those tools finds their footing.

Tiers:

- `0`: block. Credentials. Replaced always, whatever the policy says, unless a policy
  excludes the type explicitly.
- `1`: replace by default. Direct identifiers of a natural person.
- `2`: policy decides. Quasi-identifiers and sensitive attributes. The default policy
  replaces the ones that identify a party (organisation numbers and names, amounts) and keeps
  the ones the reader usually needs to reason (dates, postcodes, URLs), but reports them.

The registry is a plain dict so a caller can add a type (`ENTITY_TYPES['POLICY_NUMBER'] =
EntityType(...)`) before building detectors for it.

```pycon
>>> ENTITY_TYPES['CPR'].tier, ENTITY_TYPES['DATE'].tier
(1, 2)
```

### Module Attributes

| [`SURROGATE_TYPE`](#nyms.taxonomy.SURROGATE_TYPE)   | The pseudo-type of a span that is one of the project's own surrogates.   |
|-------------------------------------------------------------------|--------------------------------------------------------------------------|

### Functions

| [`tier_of`](#nyms.taxonomy.tier_of)(entity_type)   | The tier of a type, `2` for an unregistered one (policy decides).   |
|-------------------------------------------------------------------------|---------------------------------------------------------------------|

### Classes

| [`EntityType`](#nyms.taxonomy.EntityType)(name, identifier_class, tier[, ...])   | One entity type and its place in the taxonomy.   |
|----------------------------------------------------------------------------------------------------|--------------------------------------------------|

### *class* nyms.taxonomy.EntityType(name, identifier_class, tier, description='', aliases=tuple())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One entity type and its place in the taxonomy.

### nyms.taxonomy.SURROGATE_TYPE *= 'SURROGATE'*

The pseudo-type of a span that is one of the project’s own surrogates. Such spans take
part in overlap resolution (so a surrogate is never re-detected as a name) and are then
dropped: a policy never acts on them.

### nyms.taxonomy.tier_of(entity_type)

The tier of a type, `2` for an unregistered one (policy decides).

```pycon
>>> tier_of('CREDENTIAL'), tier_of('UNKNOWN')
(0, 2)
```

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)
