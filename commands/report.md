---
description: Generate the flightrec report for this project (HTML report + SQLite database)
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/flightrec" build --project "${CLAUDE_PROJECT_DIR:-.}"`

Tell the user, in a few lines, the path of the report generated above and the number of sessions,
actions and findings. Do not open or analyze the report unless the user asks.
