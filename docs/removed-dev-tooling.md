# Removed dev tooling (2026-08-06)

The `pre-push` hook and its lint / type-check configs were removed: none of
`isort`, `flake8`, `pyright`, or `black` were installed locally, the hook was
never symlinked into `.git/hooks`, so the gates hadn't run in practice and the
configs were dead weight.

Tests are the remaining check and run in plain Python, no Sublime instance:

```sh
py test_open_url.py
```

To restore, recreate the files below and symlink the hook:

```sh
cd .git/hooks && ln -s -f ../../pre-push
```

They also live in git history — the last commit that had them is `3.0.1`, so
`git show 3.0.1:pre-push` (or `:.flake8`, `:pyproject.toml`,
`:pyrightconfig.json`) retrieves any of them verbatim.

## `pre-push`

Mode `755`.

```bash
#!/bin/bash -e

# run from root of repo: `cd .git/hooks && ln -s -f ../../pre-push`

isort --check .
flake8 .
pyright
python3 test_open_url.py
```

Note: the README claimed this hook ran `black` too; the script never did.

## `.flake8`

```ini
[flake8]
# W191 — indentation contains tabs (we use tabs intentionally; not PEP 8)
# E101 — mixed spaces/tabs (suppressed because we use tabs for indentation; aligned comments may use spaces)
# E128 — continuation line under-indented for visual indent (irrelevant with tabs)
ignore =
  C812,
  C813,
  C814,
  E226,
  W191,
  E101,
  E128
max-line-length = 120
```

## `pyproject.toml`

Held only the isort config, so the whole file went.

```toml
[tool.isort]
indent = "\t"
line_length = 120
```

## `pyrightconfig.json`

```json
{
  "include": ["open_url.py", "url.py"],
  "useLibraryCodeForTypes": true,
  "reportOptionalSubscript": "error",
  "reportOptionalMemberAccess": "error",
  "reportOptionalCall": "error",
  "reportOptionalIterable": "error",
  "reportOptionalContextManager": "error",
  "reportOptionalOperand": "error",
  "strictListInference": true,
  "strictDictionaryInference": true,
  "typeCheckingMode": "basic",
  "reportMissingImports": true,
  "reportUnnecessaryCast": "warning",
  "reportUnnecessaryComparison": "error",
  "reportConstantRedefinition": "error",
  "reportUnnecessaryTypeIgnoreComment": "warning"
}
```

## Kept

`.python-version` (`3.8`) stays — it pins the interpreter to match [Sublime's
ST4 API environment](https://www.sublimetext.com/docs/api_environments.html),
which is runtime documentation, not a lint gate.
