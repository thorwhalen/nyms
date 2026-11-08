---
name: nyms
description: Pseudonymise documents before any of their content reaches an AI model, re-identify the model's answer, and check that nothing leaks, with the nyms package (Danish and English; CPR, CVR, names, addresses, phone, e-mail, IBAN, amounts, credentials). Use whenever a user wants to send personal, legal, medical or financial documents to an AI, asks to "anonymise", "redact", "remove names", "mask the CPR numbers", "de-identify", "pseudonymise", "protect privacy before sending to ChatGPT/Claude", or when you are about to paste someone else's personal data into a prompt. Also use to put the real names back into an answer ("re-identify", "restore the names").
metadata:
  audience: users
---

# nyms: pseudonymise, send, re-identify, check

The deterministic pass runs **before** any content reaches a model. That order is the point: the model only ever sees surrogates for what the pass caught.

## The loop

```bash
nyms pseudonymise <file> --project <project> --names "<Party One>,<Party Two>" --out <file>.pseud.md
```

1. **Pick a project name** and keep it for the whole matter (`case-2026`, `tenancy-dispute`). The project is the unit of consistency: the same person is `[PERSON_1]` in every document, and the mapping and key are stored per project (`~/.local/share/nyms/<project>/`, `~/.config/nyms/keys/<project>.key`).
2. **Pass the names you know** with `--names`: the parties, their lawyers, the company. No detector can know them; the list makes them certain.
3. **Read the report** the command returns: `replaced_by_type`, and `kept`, the spans it detected but left (dates, postcodes, URLs under the default policy). If something in `kept` should go, rerun with `--policy strict`, or pass it in `--names`.
4. **Send the `.pseud.md` file**, never the original. Before sending any other text you wrote about the matter, run `nyms check <text or file> --project <project>`; a non-empty `leaks` list is a stop.
5. **Re-identify the answer**: `nyms reidentify <answer> --project <project>`. The result lists `unmatched` tokens (ones the model invented); tell the user about them rather than guessing.

From Python, the same four verbs are `Pseudonymiser(project, names=[...]).pseudonymise / reidentify / check / detect`; `store={}` keeps a run in memory.

## What to tell the user

- "Pseudonymised, not anonymous." The mapping store and key re-identify everything; whoever has them has the originals. Never say "anonymised".
- What the pass does not catch: names it has never seen and the heuristic misses, roles, rare facts and relationships that identify someone without any identifier, inflected compounds, OCR noise. Offer `nyms detect <file>` to show every span and the decision, so the user can review before sending.
- Surrogate forms: the default `[PERSON_1]` is what models alter least; `--strategy keyed-words` gives readable pseudonyms (`Alder Brook`) that are the same on any machine with the key; `--aliases "Acme ApS=the landlord"` lets the user pick.

## Never

- Never send the original when a pseudonymised copy exists; never paste `nyms mapping` output or the mapping directory into a prompt, an issue or a chat.
- Never claim a numeric privacy guarantee. Report coverage: counts by type, what was kept, which detectors ran.
- Never resolve an `unmatched` token by guessing which person it is.
