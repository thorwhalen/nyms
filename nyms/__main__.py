"""``python -m nyms`` / ``nyms``: the CLI, built from the same functions the library exposes.

nyms pseudonymise --path letter.md --project case-2026 --names "Rasmus Jensen" --out letter.pseud.md
nyms reidentify --path answer.md --project case-2026
nyms detect "Rasmus Jensen, tlf. 12 34 56 78"   # spans and the policy's decision, nothing stored
nyms check --path draft.md --project case-2026  # would this leak?
nyms readable 010190-1234                       # a keyed hash as words
"""

import cw

from nyms.tools import _dispatch_funcs


def main() -> int:
    # Positional parameters stay positional even with a default (the text); keyword-only
    # parameters become flags (--path, --project, ...).
    return cw.dispatch(_dispatch_funcs, prog="nyms", convention=cw.Convention(naming=cw.BY_NAME_IF_KWONLY))


if __name__ == "__main__":
    raise SystemExit(main())
