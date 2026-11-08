# Security policy

## What flightrec stores

flightrec writes everything locally, under `.claude/flightrec/` in your project. That folder can contain:

- copies of every non-ignored file in the project, at every step (`snapshots.git/`);
- the full hook payloads, including tool inputs and outputs (`events.jsonl`);
- copies of Claude Code transcripts (`transcripts/`).

If secrets are present in your project and not excluded via `.gitignore` or `.flightrecignore`, they will be stored there. Never commit or share this folder.

flightrec is not tamper-proof: the recording can be modified by anything with write access to the project.

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private vulnerability reporting instead: on the repository page, go to **Security → Report a vulnerability**.

Include the flightrec version, your OS, and the steps to reproduce. You should get a reply within a few days.
