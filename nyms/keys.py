"""Key management for a single user or a small team: where the project's secret lives.

The key is the "additional information" of GDPR Art. 4(5): whoever holds it and the mapping
store can re-identify. So it never sits next to the pseudonymised text, and never inside the
mapping store's directory. Resolution order of :func:`resolve_key`:

1. the environment variable (``NYMS_KEY``, hex or base64), for CI and scripted use;
2. a per-project key file under the user's config dir (``~/.config/nyms/keys/<project>.key``,
   mode 0600), created with 32 random bytes on first use;
3. a passphrase, when one is given, derived with scrypt (stdlib) and a per-project salt
   stored next to the key file.

Replacements this seam allows: the ``keyring`` package (OS keychain), ``config2py``'s layered
resolution, ``age`` recipients, an external KMS. Each is one ``key=`` argument to the
facade. Rotation is a new project (keyed-hash surrogates change with the key by construction;
counter surrogates survive it, since they live in the store).

>>> import tempfile, os
>>> d = tempfile.mkdtemp()
>>> k1 = resolve_key('demo', key_dir=d, env_var=None)
>>> len(k1), k1 == resolve_key('demo', key_dir=d, env_var=None)
(32, True)
>>> derive_key('correct horse', salt=b'salt' * 4) == derive_key('correct horse', salt=b'salt' * 4)
True
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import secrets
from pathlib import Path

KEY_BYTES = 32
DEFAULT_ENV_VAR = "NYMS_KEY"
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**15, 8, 1
_SCRYPT_MAXMEM = 2**27  # 128 MiB: 128 * r * n bytes plus headroom


def config_dir() -> Path:
    """``$XDG_CONFIG_HOME/nyms`` or ``~/.config/nyms``."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "nyms"


def data_dir() -> Path:
    """``$XDG_DATA_HOME/nyms`` or ``~/.local/share/nyms``: where mapping stores live by default."""
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return Path(base) / "nyms"


def key_path(project: str, *, key_dir: str | os.PathLike | None = None) -> Path:
    _check_project_name(project)
    return Path(key_dir) / f"{project}.key" if key_dir else config_dir() / "keys" / f"{project}.key"


def _check_project_name(project: str) -> None:
    if not project or any(c in project for c in "/\\\0") or project in (".", ".."):
        raise ValueError(f"not a valid project name: {project!r}")


def decode_key(text: str) -> bytes:
    """A key from its hex or base64 text form.

    >>> decode_key('00' * 32) == bytes(32)
    True
    """
    text = text.strip()
    try:
        return bytes.fromhex(text)
    except ValueError:
        pass
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError("key text is neither hex nor base64") from e


def derive_key(passphrase: str, *, salt: bytes, length: int = KEY_BYTES) -> bytes:
    """scrypt key derivation (stdlib). Argon2id is the replacement when ``argon2-cffi`` is wanted."""
    return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, maxmem=_SCRYPT_MAXMEM, dklen=length)


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def resolve_key(
    project: str = "default",
    *,
    env_var: str | None = DEFAULT_ENV_VAR,
    key_dir: str | os.PathLike | None = None,
    passphrase: str | None = None,
    create: bool = True,
) -> bytes:
    """The project's key, by the resolution order in the module docstring.

    Raises ``FileNotFoundError`` when no key exists and *create* is false.
    """
    if env_var and os.environ.get(env_var):
        return decode_key(os.environ[env_var])
    path = key_path(project, key_dir=key_dir)
    if passphrase is not None:
        salt_path = path.with_suffix(".salt")
        if not salt_path.exists():
            if not create:
                raise FileNotFoundError(salt_path)
            _write_private(salt_path, secrets.token_bytes(16))
        return derive_key(passphrase, salt=salt_path.read_bytes())
    if path.exists():
        return path.read_bytes()
    if not create:
        raise FileNotFoundError(path)
    key = secrets.token_bytes(KEY_BYTES)
    _write_private(path, key)
    return key
