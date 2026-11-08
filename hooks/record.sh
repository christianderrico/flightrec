#!/usr/bin/env bash
# flightrec recorder: called by Claude Code for every event (hook).
#
#  - appends the full event to .claude/flightrec/events.jsonl
#  - for events that can change files, snapshots the project into a separate
#    Git repository (.claude/flightrec/snapshots.git) and records the tree
#  - at the end of each turn/session, archives the transcript (survives the 30-day cleanup)
#
# Never blocks Claude: any error is ignored and the script exits with 0.
# Variables: FLIGHTREC_DISABLE=1, FLIGHTREC_SNAPSHOT=0, FLIGHTREC_DIR=<directory>,
#            FLIGHTREC_KEEP_READ_OUTPUT=1 (also store the output of read-only tools)

[ "${FLIGHTREC_DISABLE:-0}" = 1 ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

IN=$(cat) || exit 0
[ -n "$IN" ] || exit 0

# a single jq call: event, tool, cwd, transcript, arrival time (with fractional seconds)
# \x1f separator: with tabs, read would merge consecutive empty fields
IFS=$'\x1f' read -r EVENT TOOL CWD TPATH ATPATH TS < <(
  printf '%s' "$IN" | jq -r '[.hook_event_name//"", .tool_name//"", .cwd//"",
     .transcript_path//"", .agent_transcript_path//"", (now|tostring)]
     | map(tostring | gsub("[\u001f\n]"; " ")) | join("\u001f")' 2>/dev/null
) || exit 0
[ -n "$EVENT" ] || exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$CWD}"
[ -n "$ROOT" ] && [ -d "$ROOT" ] || exit 0
DIR="${FLIGHTREC_DIR:-$ROOT/.claude/flightrec}"
mkdir -p "$DIR" 2>/dev/null || exit 0

# Tools that do not modify files: no snapshot (they are the most frequent, so the hook stays light)
READONLY='^(Read|Grep|Glob|LS|WebFetch|WebSearch|TodoWrite|TodoRead|ToolSearch|AskUserQuestion|ExitPlanMode|EnterPlanMode|TaskGet|TaskList|TaskCreate|TaskUpdate|TaskOutput|BashOutput|ListMcpResourcesTool|ReadMcpResourceTool)$'

SNAP=0
case "$EVENT" in
  PreToolUse|PostToolUse|PostToolUseFailure) [[ "$TOOL" =~ $READONLY ]] || SNAP=1 ;;
  SessionStart|UserPromptSubmit|Stop|SubagentStop|SessionEnd|PreCompact) SNAP=1 ;;
esac
[ "${FLIGHTREC_SNAPSHOT:-1}" = 0 ] && SNAP=0

# --- lock: tool calls can run in parallel ---------------------------------------------
LOCK="$DIR/.lock"
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK" && flock -w 20 9
else
  for _ in $(seq 1 400); do
    if mkdir "$LOCK.d" 2>/dev/null; then trap 'rmdir "$LOCK.d" 2>/dev/null' EXIT; break; fi
    # orphaned lock (killed process): older than 60 s
    if [ -n "$(find "$LOCK.d" -maxdepth 0 -mmin +1 2>/dev/null)" ]; then rmdir "$LOCK.d" 2>/dev/null; fi
    sleep 0.05
  done
fi

# --- project snapshot -------------------------------------------------------------------
TREE=""
if [ "$SNAP" = 1 ] && command -v git >/dev/null 2>&1; then
  G="$DIR/snapshots.git"
  if [ ! -d "$G" ]; then
    git init -q --bare "$G" >/dev/null 2>&1
    mkdir -p "$G/info"
  fi
  # exclusions: project .gitignore (automatic) + heavy directories + .flightrecignore
  EXC="$G/info/exclude"
  if ! grep -q '^# flightrec' "$EXC" 2>/dev/null || { [ -f "$ROOT/.flightrecignore" ] && [ "$ROOT/.flightrecignore" -nt "$EXC" ]; }; then
    {
      printf '# flightrec (regenerated automatically)\n/%s/\n' "${DIR#"$ROOT"/}"
      printf '%s\n' node_modules/ .venv/ venv/ __pycache__/ .mypy_cache/ .pytest_cache/ .next/ .nuxt/ \
        .gradle/ .terraform/ .DS_Store '*.pyc'
      [ -f "$ROOT/.flightrecignore" ] && cat "$ROOT/.flightrecignore"
    } > "$EXC" 2>/dev/null
  fi
  TREE=$(
    export GIT_DIR="$G" GIT_WORK_TREE="$ROOT" GIT_INDEX_FILE="$DIR/index" \
           GIT_AUTHOR_NAME=flightrec GIT_AUTHOR_EMAIL=flightrec@localhost \
           GIT_COMMITTER_NAME=flightrec GIT_COMMITTER_EMAIL=flightrec@localhost
    cd "$ROOT" 2>/dev/null || exit 0
    git -c core.autocrlf=false -c core.safecrlf=false add -A . >/dev/null 2>&1
    # .flightrecinclude: files ignored by .gitignore to snapshot anyway (e.g. .env, generated files)
    if [ -f "$ROOT/.flightrecinclude" ]; then
      while IFS= read -r pat || [ -n "$pat" ]; do
        pat="${pat%$'\r'}"
        case "$pat" in ''|'#'*) continue ;; esac
        git -c core.autocrlf=false -c core.safecrlf=false add -A -f -- "$pat" \
          ":(exclude)${DIR#"$ROOT"/}" >/dev/null 2>&1
      done < "$ROOT/.flightrecinclude"
    fi
    t=$(git write-tree 2>/dev/null) || exit 0
    # keep objects reachable (a commit only when the tree changes)
    prev=$(git rev-parse -q --verify refs/flightrec/snapshots 2>/dev/null)
    if [ -z "$prev" ] || [ "$(git rev-parse "$prev^{tree}" 2>/dev/null)" != "$t" ]; then
      c=$(printf '%s %s\n' "$EVENT" "$TOOL" | git commit-tree "$t" ${prev:+-p "$prev"} 2>/dev/null) \
        && git update-ref refs/flightrec/snapshots "$c" >/dev/null 2>&1
    fi
    [ "$EVENT" = SessionEnd ] && git gc --auto --quiet >/dev/null 2>&1
    printf '%s' "$t"
  )
fi

# --- event -------------------------------------------------------------------------------
KEEP=0
[[ "$TOOL" =~ $READONLY ]] && [ "${FLIGHTREC_KEEP_READ_OUTPUT:-0}" != 1 ] && KEEP=1
printf '%s' "$IN" | jq -c --arg ts "$TS" --arg tree "$TREE" --argjson drop "$KEEP" '
  {v: 1, ts: ($ts|tonumber), event: .hook_event_name, session: .session_id,
   agent: (.agent_id // null), tool: (.tool_name // null), id: (.tool_use_id // null),
   tree: (if $tree == "" then null else $tree end),
   payload: (if $drop == 1 and has("tool_response") then (.tool_response = "[omitted: read-only tool, see transcript]") else . end)}
' >> "$DIR/events.jsonl" 2>/dev/null

# --- transcript archive ----------------------------------------------------------------
case "$EVENT" in
  Stop|SessionEnd|SubagentStop|PreCompact)
    mkdir -p "$DIR/transcripts" 2>/dev/null
    for t in "$TPATH" "$ATPATH"; do
      [ -n "$t" ] && [ -f "$t" ] || continue
      sid=$(basename "$t" .jsonl)
      cp -p "$t" "$DIR/transcripts/$sid.jsonl" 2>/dev/null
      sub="${t%.jsonl}/subagents"
      if [ -d "$sub" ]; then mkdir -p "$DIR/transcripts/$sid.subagents" && cp -p "$sub"/*.jsonl "$DIR/transcripts/$sid.subagents/" 2>/dev/null; fi
    done ;;
esac

exit 0
