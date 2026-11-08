# nyms.keys

Key management for a single user or a small team: where the project’s secret lives.

The key is the “additional information” of GDPR Art. 4(5): whoever holds it and the mapping
store can re-identify. So it never sits next to the pseudonymised text, and never inside the
mapping store’s directory. Resolution order of [`resolve_key()`](#nyms.keys.resolve_key):

1. the environment variable (`NYMS_KEY`, hex or base64), for CI and scripted use;
2. a per-project key file under the user’s config dir (`~/.config/nyms/keys/<project>.key`,
   mode 0600), created with 32 random bytes on first use;
3. a passphrase, when one is given, derived with scrypt (stdlib) and a per-project salt
   stored next to the key file.

Replacements this seam allows: the `keyring` package (OS keychain), `config2py`’s layered
resolution, `age` recipients, an external KMS. Each is one `key=` argument to the
facade. Rotation is a new project (keyed-hash surrogates change with the key by construction;
counter surrogates survive it, since they live in the store).

```pycon
>>> import tempfile, os
>>> d = tempfile.mkdtemp()
>>> k1 = resolve_key('demo', key_dir=d, env_var=None)
>>> len(k1), k1 == resolve_key('demo', key_dir=d, env_var=None)
(32, True)
>>> derive_key('correct horse', salt=b'salt' * 4) == derive_key('correct horse', salt=b'salt' * 4)
True
```

### Functions

| [`config_dir`](#nyms.keys.config_dir)()                                  | `$XDG_CONFIG_HOME/nyms` or `~/.config/nyms`.                                          |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| [`data_dir`](#nyms.keys.data_dir)()                                    | `$XDG_DATA_HOME/nyms` or `~/.local/share/nyms`: where mapping stores live by default. |
| [`decode_key`](#nyms.keys.decode_key)(text)                              | A key from its hex or base64 text form.                                               |
| [`derive_key`](#nyms.keys.derive_key)(passphrase, \*, salt[, length])    | scrypt key derivation (stdlib).                                                       |
| `key_path`(project, \*[, key_dir])                                                             |                                                                                       |
| [`resolve_key`](#nyms.keys.resolve_key)([project, env_var, key_dir, ...]) | The project's key, by the resolution order in the module docstring.                   |

### nyms.keys.config_dir()

`$XDG_CONFIG_HOME/nyms` or `~/.config/nyms`.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### nyms.keys.data_dir()

`$XDG_DATA_HOME/nyms` or `~/.local/share/nyms`: where mapping stores live by default.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### nyms.keys.decode_key(text)

A key from its hex or base64 text form.

```pycon
>>> decode_key('00' * 32) == bytes(32)
True
```

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### nyms.keys.derive_key(passphrase, , salt, length=32)

scrypt key derivation (stdlib). Argon2id is the replacement when `argon2-cffi` is wanted.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### nyms.keys.resolve_key(project='default', , env_var='NYMS_KEY', key_dir=None, passphrase=None, create=True)

The project’s key, by the resolution order in the module docstring.

Raises `FileNotFoundError` when no key exists and *create* is false.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)
