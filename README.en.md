# DevReport

**Language:** [Русский](README.md) | **English**

Repository: [github.com/SirEdwinDrow/DevReport](https://github.com/SirEdwinDrow/DevReport)

DevReport is a small cross-platform CLI utility for preparing diagnostic reports about a project's local environment (Windows and Linux).

Typical flow: open a terminal in the project directory → `devreport collect` → get a short diagnosis → optionally attach a log explicitly → review sensitive-data warnings → attach the Markdown report to an Issue or send it to a colleague.

This is **not** a vulnerability scanner, **not** an auto-fixer, and **not** a cloud/telemetry service.

## MVP limitations

- Logs are read only when explicitly requested (`--log`); without the flag, logs are not read.
- `.env` values never appear in the report (only key names are compared).
- The Docker daemon is not checked (`docker ps` / `docker info` are not run).
- Port checks use `127.0.0.1` (IPv4) only; IPv6 is not checked.
- Multiline and complex dotenv syntax are only partially supported.
- Automatic redaction is **incomplete**: it does not remove every secret (non-standard key names, free-form text) — always review the report manually before publishing.
- Commands from the inspected project directory are not executed.
- Supported platforms: Windows 10/11 and Linux.

## Install from a local checkout

Requires Python 3.11+.

### Windows (PowerShell)

```powershell
cd d:\projects\DevReport
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

### Linux (bash)

```bash
cd /path/to/DevReport
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Run:

```text
devreport --help
python -m devreport --help
```

Installing from PyPI is **not** documented here as a guaranteed method: publish/install from a source checkout.

CLI help and runtime messages in this MVP are in Russian; identifiers and machine-readable codes are in English.

## `collect` options

| Option | Default | Description |
| --- | --- | --- |
| `--project` | current directory | Project root |
| `--port` | unset | TCP bind check on 127.0.0.1 |
| `--log` | unset | Explicitly include a log file tail |
| `--tail` | 50 (or from config) | Number of log lines (1–1000) |
| `--format` | markdown | `markdown` or `json` |
| `--output` / `-o` | none | Write the report to a file |
| `--preview` | false | Show the report without writing a file |
| `--force` | false | Overwrite an existing `--output` file |

Without `--output`, the full report goes to **stdout**; the short summary and warnings go to **stderr**.  
Using `--preview` and `--output` together is an argument error.

Project config: `.devreport.toml` in the project root (CLI > config > built-in defaults).

## Examples

```text
devreport collect
devreport collect --project .
devreport collect --port 8000
devreport collect --log ./examples/sample.log --tail 50
devreport collect --format markdown --output ./report.md
devreport collect --format json --output ./report.json
devreport collect --preview
devreport collect --output ./report.md --force
python -m devreport collect --help
```

## Sample Markdown fragment

```markdown
# DevReport

- schema_version: `1.0`
- tool_version: `0.1.0`

> Automatic redaction is incomplete: it does not remove every secret. Always review the report manually before publishing.

## System
- OS: Windows / ...
- Python: 3.11.x
```

Report `schema_version`: **`1.0`**.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Report produced (even if checks contain warning/error) |
| 1 | Internal error or inability to write the report |
| 2 | Invalid CLI arguments or configuration |

Missing Git/Docker/`.env` alone does not yield exit code 1.

## Privacy

- Hostname, username, interface MAC/IP addresses, full `sys.executable`, and the process environment map are not collected.
- SSH keys, credential stores, and home directories contents are not read wholesale.
- There is no network upload and no telemetry.
- The redaction alias mapping exists only in memory and is not written into the report.

**Warning:** automatic redaction is incomplete and does not remove every secret (non-standard key names, free-form text, unknown formats). Always review the report manually before publishing.

## Tests and quality

```text
ruff check src tests
ruff format --check src tests
mypy
pytest
```

## Known limitations

See “MVP limitations” above and the “Diagnostic limitations” section in every report.
