# Contributing to flightrec

Thanks for your interest. Bug reports, transcripts that break the parser, and small focused pull requests are all welcome.

## Before you open a pull request

1. Run the test suite (it needs `bash`, `jq`, `git` and Python 3.9+):

   ```bash
   tests/run_all.sh
   ```

2. Keep the design constraints intact:
   - **No dependencies.** `bin/flightrec` uses only the Python standard library; the hook uses only `bash`, `jq` and `git`.
   - **Hooks never get in the way.** `hooks/record.sh` must never write to stdout, never block Claude Code and always exit 0.
   - **Deterministic report.** Every finding comes from a fixed rule and cites its evidence. No LLM calls.
   - **The user's Git repository is never touched.** Snapshots live only in `.claude/flightrec/snapshots.git`.
3. If you add or change a finding, add a step to `tests/scenario.py` that triggers it.

## Reporting a parser bug

New Claude Code versions sometimes change the transcript format. If `flightrec build` misreads a session, open an issue with the Claude Code version and, if possible, a minimal transcript excerpt. **Remove any secrets, file contents or personal data first.**
