---
description: Genera il resoconto flightrec di questo progetto (report HTML + database SQLite)
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/bin/flightrec" build --project "${CLAUDE_PROJECT_DIR:-.}"`

Riporta all'utente, in poche righe, il percorso del report generato qui sopra e il numero di sessioni,
azioni e segnalazioni. Non aprire né analizzare il report a meno che l'utente non lo chieda.
