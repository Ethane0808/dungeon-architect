# Agent test execution

On Windows, sandbox agents may run as a different account while sharing the
desktop user's TEMP and project directory. Python/pytest can create private
directories that the desktop user cannot access.

For sandbox test runs, isolate both temporary files and the pytest cache with
fresh paths. Keep warning reporting enabled:

```powershell
$agentPytestTemp = Join-Path $env:TEMP ('dungeon-architect-agent-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -ra -W default --basetemp $agentPytestTemp -o "cache_dir=$agentPytestTemp-cache"
```

Use a new generated path for every run: pytest clears an existing `--basetemp`.
Never point it at a project root or any shared default temporary directory.
Do not use the desktop user's `pytest-of-*` or `.pytest_cache` directories from
the sandbox. When reproducing a desktop-account problem, run the user's exact
command in that account through the approved execution mechanism.
