# nyms: agent map

Seams (one keyword argument each, ADR 0001): `detectors` (default: regex/checksum/gazetteer; model pass not built), `policy` (default preset), `strategy` (`Counter`, `[PERSON_1]`), `store` (`dol.JsonFiles` under the user data dir), `key` (env var, key file). Surfaces built: Python facade, CLI (`cw` over `nyms/tools.py`), shipped skill. Not built: MCP, HTTP.

Dev skill: `nyms-dev-deidentification` (`skills/`), the index to `docs/research/` and `docs/adr/`. Shipped skill: `nyms` (`nyms/data/skills/`). Both are linked from `.claude/skills/`.

Rules: say pseudonymise, never anonymise. Fixtures are synthetic; no real data in this public repo. Never relax the leakage, round-trip, consistency and prefix-safety tests. A new detector needs a taxonomy entry, a fixture value and an `expected.json` line.
