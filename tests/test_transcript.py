#!/usr/bin/env python3
"""The parser must correctly read a transcript produced by Claude Code 2.1.319.

The fixture is a real (Italian-language) session, kept verbatim."""
import importlib.machinery, importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
loader = importlib.machinery.SourceFileLoader("flightrec", os.path.join(HERE, "..", "bin", "flightrec"))
spec = importlib.util.spec_from_loader("flightrec", loader)
fr = importlib.util.module_from_spec(spec)
loader.exec_module(fr)

meta, prompts, calls = fr.parse_transcript(os.path.join(HERE, "fixtures", "claude_code_2.1.319.jsonl"), "/tmp/fr-sandbox")
got = [(c["tool"], c["status"]) for c in calls]
want = [("Read", "ok"), ("Edit", "ok"), ("Bash", "error"), ("Bash", "ok"), ("Edit", "error"), ("Read", "ok")]
checks = [
    (got == want, f"calls and statuses: {got}"),
    ([p["text"] for p in prompts] == ["fai il test"], f"prompt: {[p['text'] for p in prompts]}"),
    (calls[1]["intent"] == "Sostituisco beta con gamma.", f"Edit intent: {calls[1]['intent']!r}"),
    (all(c["result_ts"] and c["requested"] for c in calls), "request and result timestamps present"),
    (calls[1]["tool_use_result"].get("oldString") == "beta", "toolUseResult parsed"),
]
ok = True
for cond, msg in checks:
    print(("PASS " if cond else "FAIL ") + msg)
    ok &= bool(cond)
sys.exit(0 if ok else 1)
