# flightrec

**Una scatola nera per Claude Code.** Registra ogni azione dell'agente, verifica cosa è cambiato davvero sul disco
e produce un resoconto deterministico (senza LLM) che puoi consultare offline: una pagina HTML e un database SQLite.

```
» PROMPT: Rinomina beta in gamma e sistema il progetto
  ✓ #2   10:02:43   0.0s Edit: notes.txt
        ↳ M:notes.txt(+1/-1)
  ✗ #3   10:02:43   0.0s Bash: cat missing_file.txt
        ⚠ Bash è fallito: Exit code 1
  ✓ #4   10:02:43   0.1s Bash: echo hi > made_by_bash.txt && sed -i 's/alpha/ALPHA/' notes.txt
        ↳ A:made_by_bash.txt(+1/-0) M:notes.txt(+1/-1)
        ⚠ Bash ha modificato 2 file: made_by_bash.txt, notes.txt
  ✓ #5   10:02:43   0.0s Edit: app.py
        ⚠ Edit riuscito ma app.py non è cambiato sul disco
  ✎ 10:02:43        modificati fuori da Claude: notes.txt(+1/-0)
  ✓ #16  10:02:44   0.1s Edit: app.py
        ⚠ app.py riportato a una versione precedente: annulla il lavoro dal passo 6
```

## Perché

Il transcript di Claude Code dice cosa l'agente *voleva* fare. Gli hook dicono *quando* l'ha fatto.
Solo il disco dice cosa è *successo davvero*: un `sed -i` dentro un comando Bash, un file creato e poi
cancellato, una Edit che risulta riuscita ma non cambia nulla, una modifica fatta da te tra un turno e l'altro.

flightrec incrocia le tre fonti, unite per `session_id` + `tool_use_id`:

| Fonte | Cosa fornisce |
|---|---|
| Transcript di Claude Code | intenzione (testo e ragionamento prima dell'azione), input, risultato |
| Hook `PreToolUse` / `PostToolUse` / `PostToolUseFailure` | orari precisi, durata, esito |
| Foto del progetto in un git separato | diff reale di ogni azione, anche di quelle fatte via Bash |

## Installazione

Requisiti: `bash`, `jq`, `git`, `python3` (3.8+). Nessuna dipendenza Python.

Dentro Claude Code:

```
/plugin marketplace add donerrico99/flightrec
/plugin install flightrec@flightrec
```

Oppure, per provarlo senza installarlo: `claude --plugin-dir /percorso/flightrec`.

Da quel momento ogni sessione nel progetto viene registrata in `.claude/flightrec/`.
Aggiungi questa riga al `.gitignore` del progetto:

```
.claude/flightrec/
```

## Uso

```
/flightrec:report                                       # dentro Claude Code: genera il report
python3 <plugin>/bin/flightrec build                    # report.html + flightrec.db in .claude/flightrec/
python3 <plugin>/bin/flightrec sessions                 # elenco sessioni
python3 <plugin>/bin/flightrec timeline [SESSIONE] -v   # cronologia nel terminale (con -v anche cosa ha detto)
python3 <plugin>/bin/flightrec diff <tool_use_id>       # diff reale di una singola azione
python3 <plugin>/bin/flightrec findings                 # solo le segnalazioni
```

Funziona anche sulle sessioni registrate **prima** di installare flightrec: legge lo storico di Claude Code
(`~/.claude/projects/`), ma in quel caso gli effetti sui file sono quelli dichiarati nel transcript e
il report li segna come *non verificati*.

## Segnalazioni

Tutte prodotte da regole fisse, ognuna con le prove (id delle chiamate, file, passi):

| Tipo | Quando |
|---|---|
| `tool_error` | un tool è fallito |
| `identical_retry` / `retry_loop` | stesso tool con input identico dopo un errore (3+ volte = loop) |
| `no_effect` | Edit/Write riuscito ma il file sul disco non è cambiato |
| `indirect_change` | un comando Bash (o altro tool) ha modificato file |
| `side_effect` | una Edit ha cambiato anche file diversi da quello dichiarato |
| `error_with_changes` | un'azione risulta fallita ma ha cambiato file |
| `reverted` | un file torna a una versione precedente della sessione (lavoro annullato), o viene eliminato dopo essere stato creato |
| `repeated_read` | lo stesso file letto 3 volte senza modifiche in mezzo |
| `external_change` | file cambiati fuori dalle azioni di Claude (tu, l'editor, un altro processo) |
| `shared_attribution` | file cambiati mentre giravano chiamate parallele |
| `slow` | azione oltre 60 secondi |
| `interrupted`, `denied`, `no_result`, `user_interrupt` | interruzioni e permessi negati |

## Cosa salva e dove

```
.claude/flightrec/
  events.jsonl        un evento per riga (payload completo degli hook)
  snapshots.git/      foto del progetto (git separato, deduplicato e compresso)
  transcripts/        copia dei transcript, così sopravvivono alla pulizia dei 30 giorni
  report.html         generato da `flightrec build`
  flightrec.db        idem: tabelle sessions, prompts, calls, file_changes, external_changes, findings
```

- Le foto rispettano il `.gitignore` del progetto ed escludono di default `node_modules/`, `.venv/`,
  `__pycache__/` e simili. Altre esclusioni in `.flightrecignore` (stessa sintassi del `.gitignore`).
- Il git del tuo progetto non viene mai toccato.
- Le foto si fanno solo per i tool che possono modificare file e a inizio/fine turno; Read, Grep,
  Glob e simili registrano solo l'evento. L'output dei tool di sola lettura non viene duplicato
  (è già nel transcript); `FLIGHTREC_KEEP_READ_OUTPUT=1` per salvarlo comunque.

**Privacy.** Tutto resta in locale. I file contengono ciò che contiene il tuo progetto e ciò che Claude
ha letto e scritto: non committare `.claude/flightrec/`.

## Prestazioni

Misurate su un repository di 2.200 file (37 MB): prima foto 1,5 s, poi circa 30 ms per azione;
Read e simili circa 15 ms. Il hook non scrive mai su stdout e non blocca mai Claude: se qualcosa va storto
esce in silenzio.

## Variabili d'ambiente

| Variabile | Effetto |
|---|---|
| `FLIGHTREC_DISABLE=1` | non registra nulla |
| `FLIGHTREC_SNAPSHOT=0` | solo eventi, nessuna foto del disco |
| `FLIGHTREC_DIR` | cartella dei dati (default `.claude/flightrec`) |
| `FLIGHTREC_KEEP_READ_OUTPUT=1` | salva anche l'output dei tool di sola lettura |

## Limiti noti

- Con chiamate parallele le modifiche avvenute nello stesso intervallo sono attribuite a tutte
  (segnalato come `shared_attribution`).
- I processi lanciati in background da Bash che modificano file dopo la fine del comando vengono
  rilevati come `external_change` al passo successivo.
- I file ignorati dal `.gitignore` non vengono fotografati: le loro modifiche non compaiono.

## Test

```
tests/run_all.sh
```

Il test di scenario esegue il vero hook su un progetto temporaneo simulando una sessione completa
(errori, retry, effetti di Bash, chiamate parallele, modifiche esterne, lavoro annullato) e verifica
ogni segnalazione. Il test del parser usa un transcript reale di Claude Code 2.1.319.

## Licenza

MIT
