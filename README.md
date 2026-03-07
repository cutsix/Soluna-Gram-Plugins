# Soluna-Gram-Plugins

Soluna-Gram official external plugin repository.

This repository is designed for Soluna-Gram's `,apt install <plugin_name>` workflow.
The main repository fetches plugin metadata from `list.json` and downloads plugin code
from `{plugin_name}/main.py`.

## Structure

```text
{plugin_name}/
├── main.py
└── DES.md
```

- `main.py` is required and is the only file installed by `,apt install`.
- `DES.md` is optional and used as repository-side documentation.
- Extra assets are not installed by the current plugin manager. Keep plugins
  single-file, or let the plugin fetch external resources at runtime.

## Development Rules

### Imports

```python
from solgram.listener import listener
from solgram.enums import Client, Message
from solgram.utils import lang
from solgram import log
```

- Use `solgram.*` imports only.
- Do not depend on `solgram.web`.
- Python dependencies should be handled by the plugin itself when needed.
- System dependencies should be documented in `DES.md`.

### Listener

```python
@listener(
    outgoing=True,
    command="command_name",
    need_admin=True,
    description="One line description",
    parameters="[arguments]",
)
async def handler(bot: Client, message: Message):
    ...
```

- Do not explicitly pass `is_plugin`.
- Plugin-specific description text should be hardcoded instead of adding new
  `lang()` keys unless the text is shared across the main repository.

### Versions

- `list.json` versions must be numeric decimal strings such as `1.0`, `1.01`,
  `1.02`.
- Do not use semver strings like `0.1.0`, `v1`, or suffixes like `-beta`.
- The current main repository parses plugin versions as `float`.

## Publishing

1. Add the plugin directory.
2. Update `list.json`.
3. Push to the `main` branch.
