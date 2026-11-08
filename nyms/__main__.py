"""``python -m nyms`` / ``nyms``: the CLI, built from the same functions the library exposes.

nyms pseudonymise letter.md --project case-2026 --names "Rasmus Jensen" --out letter.pseud.md
nyms reidentify answer.md --project case-2026
nyms detect letter.md                       # spans and the policy's decision, nothing stored
nyms check draft.md --project case-2026     # would this leak?
nyms readable 010190-1234                   # a keyed hash as words
"""

import cw

from nyms.tools import _dispatch_funcs


def main() -> int:
    return cw.dispatch(_dispatch_funcs, prog="nyms")


if __name__ == "__main__":
    raise SystemExit(main())
