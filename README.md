<div align="center">

<img src="assets/flightrec-logo.svg" width="150" alt="flightrec logo">

# flightrec

### The black box for Claude Code.

Record every action. Verify every change.
Understand what really happened.

[GitHub](https://github.com/donerrico99/flightrec) ·
[Installation](#installation) ·
[Documentation](#usage) ·
[Issues](https://github.com/donerrico99/flightrec/issues)

![License](https://img.shields.io/github/license/donerrico99/flightrec)
![GitHub Stars](https://img.shields.io/github/stars/donerrico99/flightrec)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)

</div>

---

Records every agent action, verifies what actually changed on disk, and produces a deterministic report (no LLM required) that you can inspect offline: an HTML page and an SQLite database.

```text
» PROMPT: Rename beta to gamma and clean up the project
  ✓ #2   10:02:43   0.0s Edit: notes.txt
        ↳ M:notes.txt(+1/-1)
  ✗ #3   10:02:43   0.0s Bash: cat missing_file.txt
        ⚠ Bash failed: Exit code 1
  ✓ #4   10:02:43   0.1s Bash: echo hi > made_by_bash.txt && sed -i 's/alpha/ALPHA/' notes.txt
        ↳ A:made_by_bash.txt(+1/-0) M:notes.txt(+1/-1)
        ⚠ Bash modified 2 files: made_by_bash.txt, notes.txt
  ✓ #5   10:02:43   0.0s Edit: app.py
        ⚠ Edit succeeded but app.py was not changed on disk
  ✎ 10:02:43        modified outside Claude: notes.txt(+1/-0)
  ✓ #16  10:02:44   0.1s Edit: app.py
        ⚠ app.py reverted to a previous version: undoing work from step 6
```

## Why

Claude Code's transcript tells you what the agent *intended* to do. Hooks tell you *when* it happened. Only the filesystem tells you what *actually happened*: a `sed -i` command inside Bash, a file created and then deleted, an Edit that reports success but changes nothing, or a modification you made between turns.

flightrec correlates these three sources using `session_id` + `tool_use_id`:

| Source | What it provides |
|---|---|
| Claude Code transcript | Intent (text and reasoning before the action), input, and result |
| `PreToolUse` / `PostToolUse` / `PostToolUseFailure` hooks | Precise timestamps, duration, and outcome |
| Project snapshots stored in a separate Git repository | Actual diffs for every action, including those performed through Bash |

## Installation

Requirements: `bash`, `jq`, `git`, `python3` (3.8+). No Python dependencies.

Inside Claude Code:

```bash
/plugin marketplace add donerrico99/flightrec
/plugin install flightrec@flightrec
```

Alternatively, try it without installing:

```bash
claude --plugin-dir /path/to/flightrec
```

From that point on, every session in the project is recorded under `.claude/flightrec/`.

Add the following line to your project's `.gitignore`:

```gitignore
.claude/flightrec/
```

## Usage

```bash
/flightrec:report                                       # inside Claude Code: generate the report
python3 <plugin>/bin/flightrec build                    # generate report.html + flightrec.db in .claude/flightrec/
python3 <plugin>/bin/flightrec sessions                 # list recorded sessions
python3 <plugin>/bin/flightrec timeline [SESSION] -v    # print the timeline (-v also shows what Claude said)
python3 <plugin>/bin/flightrec diff <tool_use_id>       # show the actual diff for a single action
python3 <plugin>/bin/flightrec findings                 # show findings only
```

flightrec also works with sessions recorded **before** installation: it reads Claude Code's history from `~/.claude/projects/`. In this case, however, file changes are based on what the transcript reports rather than independently verified filesystem snapshots, and the report explicitly marks them as *unverified*.

## Findings

All findings are generated using deterministic rules, each backed by evidence (call IDs, files, and steps):

| Type | When it is triggered |
|---|---|
| `tool_error` | A tool call fails |
| `identical_retry` / `retry_loop` | The same tool is called again with identical input after an error (3+ consecutive retries = loop) |
| `no_effect` | An Edit/Write succeeds, but the file on disk remains unchanged |
| `indirect_change` | A Bash command (or another tool) modifies files |
| `side_effect` | An Edit also modifies files other than the one explicitly targeted |
| `error_with_changes` | An action reports failure but still modifies files |
| `reverted` | A file returns to a previous version from the same session (work is undone), or is deleted after being created |
| `repeated_read` | The same file is read 3 times without any intervening modifications |
| `external_change` | Files are modified outside Claude's actions (by you, an editor, or another process) |
| `shared_attribution` | Files are modified while parallel tool calls are running |
| `slow` | An action takes longer than 60 seconds |
| `interrupted`, `denied`, `no_result`, `user_interrupt` | Interruptions and permission denials |

## What gets stored and where

```text
.claude/flightrec/
  events.jsonl        one event per line (complete hook payload)
  snapshots.git/      project snapshots (separate Git repository, deduplicated and compressed)
  transcripts/        transcript copies, preserved beyond Claude Code's 30-day cleanup period
  report.html         generated by `flightrec build`
  flightrec.db        generated by `flightrec build`: sessions, prompts, calls,
                      file_changes, external_changes, and findings tables
```

- Snapshots respect your project's `.gitignore` and exclude `node_modules/`, `.venv/`, `__pycache__/`, and similar directories by default. Additional exclusions can be configured in `.flightrecignore` (using the same syntax as `.gitignore`).
- Your project's Git repository is never touched.
- Snapshots are created only for tools that can modify files and at the beginning/end of each turn. Read, Grep, Glob, and similar tools only generate events. Read-only tool output is not duplicated (it is already available in the transcript); set `FLIGHTREC_KEEP_READ_OUTPUT=1` to store it anyway.

**Privacy.** Everything stays local. The files contain whatever your project contains, as well as what Claude has read and written. Do not commit `.claude/flightrec/`.

## Performance

Benchmarked on a repository containing 2,200 files (37 MB): the initial snapshot takes 1.5 seconds, subsequent snapshots take approximately 30 ms per action, and Read-like operations take approximately 15 ms.

Hooks never write to stdout and never block Claude Code: if anything goes wrong, they fail silently.

## Environment variables

| Variable | Effect |
|---|---|
| `FLIGHTREC_DISABLE=1` | Disable recording entirely |
| `FLIGHTREC_SNAPSHOT=0` | Record events only, without filesystem snapshots |
| `FLIGHTREC_DIR` | Data directory (default: `.claude/flightrec`) |
| `FLIGHTREC_KEEP_READ_OUTPUT=1` | Also store the output of read-only tools |

## Known limitations

- With parallel calls, modifications occurring within the same time window are attributed to all overlapping calls (reported as `shared_attribution`).
- Background processes launched by Bash that modify files after the command has finished are detected as `external_change` at the next step.
- Files ignored by `.gitignore` are not included in snapshots, so changes to them are not detected.

## Tests

```bash
tests/run_all.sh
```

The scenario test runs the actual hook against a temporary project, simulating a complete session (errors, retries, Bash side effects, parallel calls, external modifications, and reverted work) and verifies every finding.

The parser test uses a real Claude Code 2.1.319 transcript.

## License

MIT
