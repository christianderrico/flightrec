#!/usr/bin/env python3
"""flightrec end-to-end test.

Simulates a Claude Code session: for every action it calls the real hooks/record.sh
with the documented payloads, actually performs the effect on files and writes the
transcript in Claude Code's format. Then it runs the analyzer and checks the findings.
"""
import json, os, shutil, subprocess, sys, tempfile, time, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RECORD = os.path.join(ROOT, "hooks", "record.sh")
FLIGHTREC = os.path.join(ROOT, "bin", "flightrec")


class Session:
    def __init__(self, proj):
        self.proj = proj
        self.sid = str(uuid.uuid4())
        self.tdir = os.path.join(proj, "_cc_home")
        os.makedirs(self.tdir, exist_ok=True)
        self.tpath = os.path.join(self.tdir, self.sid + ".jsonl")
        self.parent = None
        self.n = 0

    # ---- transcript (Claude Code format) ----
    def _line(self, typ, content, **extra):
        u = str(uuid.uuid4())
        ln = {"parentUuid": self.parent, "isSidechain": False, "userType": "external", "cwd": self.proj,
              "sessionId": self.sid, "version": "2.1.319", "gitBranch": "main", "type": typ,
              "message": content, "uuid": u, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + ".%03dZ" % (int(time.time() * 1000) % 1000)}
        ln.update(extra)
        self.parent = u
        with open(self.tpath, "a") as f:
            f.write(json.dumps(ln) + "\n")

    def hook(self, event, **kw):
        p = {"session_id": self.sid, "transcript_path": self.tpath, "cwd": self.proj,
             "permission_mode": "default", "hook_event_name": event}
        p.update(kw)
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.proj)
        r = subprocess.run([RECORD], input=json.dumps(p).encode(), env=env, capture_output=True, timeout=30)
        assert r.returncode == 0, r.stderr
        assert r.stdout == b"", "the hook must not write to stdout"

    def prompt(self, text):
        self.hook("UserPromptSubmit", prompt=text)
        self._line("user", {"role": "user", "content": text}, promptId=str(uuid.uuid4()))
        time.sleep(0.02)

    def say(self, text):
        self._line("assistant", {"id": "msg_" + uuid.uuid4().hex[:8], "type": "message", "role": "assistant",
                                 "model": "claude-test", "content": [{"type": "text", "text": text}],
                                 "usage": {"input_tokens": 100, "output_tokens": 20}})

    def tool(self, name, inp, effect=None, result="ok", error=False, parallel=False):
        """Run a complete action (or return the functions to run it in parallel)."""
        self.n += 1
        tid = "toolu_%02d_%s" % (self.n, uuid.uuid4().hex[:6])
        self._line("assistant", {"id": "msg_" + uuid.uuid4().hex[:8], "type": "message", "role": "assistant",
                                 "model": "claude-test",
                                 "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}],
                                 "usage": {"input_tokens": 100, "output_tokens": 30}})

        def pre():
            self.hook("PreToolUse", tool_name=name, tool_input=inp, tool_use_id=tid)

        def run():
            if effect:
                effect()
            time.sleep(0.02)

        def post():
            if error:
                self.hook("PostToolUseFailure", tool_name=name, tool_input=inp, tool_use_id=tid, error=result, is_interrupt=False)
            else:
                self.hook("PostToolUse", tool_name=name, tool_input=inp, tool_use_id=tid, tool_response={"success": True, "output": result})
            self._line("user", {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid,
                                                             "content": result, "is_error": error}]},
                       toolUseResult=("Error: " + result) if error else {"ok": True})

        if parallel:
            return tid, pre, run, post
        pre(); run(); post()
        return tid

    def stop(self):
        self.hook("Stop", stop_hook_active=False)

    def end(self):
        self.hook("SessionEnd", reason="exit")


def W(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def sh(cmd, cwd):
    return lambda: subprocess.run(cmd, shell=True, cwd=cwd)


def main():
    keep = "--keep" in sys.argv
    proj = tempfile.mkdtemp(prefix="flightrec-test-")
    try:
        subprocess.run(["git", "init", "-q"], cwd=proj)
        W(f"{proj}/notes.txt", "alpha\nbeta\n")
        W(f"{proj}/app.py", "def main():\n    return 1\n")
        W(f"{proj}/config.toml", "debug = false\n")
        W(f"{proj}/.gitignore", "secret.env\nlocal.env\n_cc_home/\n")
        W(f"{proj}/secret.env", "TOKEN=xyz\n")
        # local.env is ignored by git but explicitly included in snapshots
        W(f"{proj}/local.env", "PORT=1\n")
        W(f"{proj}/.flightrecinclude", "# ignored files to snapshot anyway\nlocal.env\n")
        s = Session(proj)
        s.hook("SessionStart", source="startup")
        P = lambda *a: os.path.join(proj, *a)

        s.prompt("Rename beta to gamma and clean up the project")
        s.say("Reading the file to understand its content.")
        s.tool("Read", {"file_path": P("notes.txt")}, result="1\talpha\n2\tbeta\n")
        s.say("Replacing beta with gamma.")
        s.tool("Edit", {"file_path": P("notes.txt"), "old_string": "beta", "new_string": "gamma"},
               effect=lambda: W(P("notes.txt"), "alpha\ngamma\n"), result="The file notes.txt has been updated successfully.")
        s.tool("Bash", {"command": "cat missing_file.txt"}, result="Exit code 1\ncat: missing_file.txt: No such file or directory", error=True)
        s.say("Creating a file from the shell.")
        s.tool("Bash", {"command": "echo hi > made_by_bash.txt && sed -i 's/alpha/ALPHA/' notes.txt"},
               effect=sh("echo hi > made_by_bash.txt && sed -i 's/alpha/ALPHA/' notes.txt", proj), result="")
        # Edit that reports success but changes nothing
        s.tool("Edit", {"file_path": P("app.py"), "old_string": "return 1", "new_string": "return 2"}, result="updated successfully")
        # two actions in parallel
        s.say("Updating app.py and creating b.txt in parallel.")
        a = s.tool("Edit", {"file_path": P("app.py"), "old_string": "return 1", "new_string": "return 3"},
                   effect=lambda: W(P("app.py"), "def main():\n    return 3\n"), parallel=True)
        b = s.tool("Bash", {"command": "touch b.txt"}, effect=sh("touch b.txt", proj), parallel=True)
        a[1](); b[1](); a[2](); b[2](); a[3](); b[3]()
        s.say("Done.")
        s.stop()

        # the user edits files between turns (including ignored ones)
        W(P("notes.txt"), "ALPHA\ngamma\ndelta (written by hand)\n")
        W(P("secret.env"), "TOKEN=changed\n")
        W(P("local.env"), "PORT=2\n")

        s.prompt("Try creating tmp.txt and then remove it; update config")
        s.tool("Write", {"file_path": P("tmp.txt"), "content": "temporary\n"},
               effect=lambda: W(P("tmp.txt"), "temporary\n"), result="File created successfully")
        s.tool("Bash", {"command": "rm tmp.txt"}, effect=sh("rm tmp.txt", proj), result="")
        bad = {"file_path": P("config.toml"), "old_string": "debug = true", "new_string": "debug = false"}
        s.tool("Edit", bad, result="<tool_use_error>String to replace not found in file.</tool_use_error>", error=True)
        s.tool("Edit", bad, result="<tool_use_error>String to replace not found in file.</tool_use_error>", error=True)
        for _ in range(3):
            s.tool("Read", {"file_path": P("config.toml")}, result="1\tdebug = false\n")
        s.tool("Bash", {"command": "echo x >> config.toml && false"},
               effect=sh("echo x >> config.toml", proj), result="Exit code 1", error=True)
        # reverted work: app.py goes back to how it was before the parallel step
        s.tool("Edit", {"file_path": P("app.py"), "old_string": "return 3", "new_string": "return 1"},
               effect=lambda: W(P("app.py"), "def main():\n    return 1\n"), result="updated successfully")
        s.say("Finished.")
        s.stop()
        s.end()

        # ---- analysis
        env = dict(os.environ, HOME=os.path.join(proj, "_fakehome"))
        r = subprocess.run([sys.executable, FLIGHTREC, "build", "--project", proj], capture_output=True, text=True, env=env)
        print(r.stdout, r.stderr)
        assert r.returncode == 0
        import sqlite3
        db = sqlite3.connect(os.path.join(proj, ".claude/flightrec/flightrec.db"))
        kinds = [k for (k,) in db.execute("SELECT kind FROM findings")]
        print("findings:", sorted(set(kinds)))
        calls = db.execute("SELECT count(*), sum(fs_verified) FROM calls").fetchone()
        print("actions:", calls)
        expect = {"tool_error", "indirect_change", "no_effect", "shared_attribution", "external_change",
                  "reverted", "identical_retry", "repeated_read", "error_with_changes"}
        missing = expect - set(kinds)
        ext = [p for (p,) in db.execute("SELECT path FROM external_changes")]
        checks = [
            (not missing, f"missing findings: {missing}"),
            (calls[0] == 16 and calls[1] == 12, f"16 actions, 12 verified on disk (the 4 Reads take no snapshot): {calls}"),
            (sorted(ext) == ["local.env", "notes.txt"], f"external changes: notes.txt and local.env (included via .flightrecinclude); secret.env ignored, the recorder does not snapshot itself: {ext[:5]}"),
            (os.path.exists(os.path.join(proj, ".claude/flightrec/transcripts", s.sid + ".jsonl")), "transcript archived in the flightrec directory"),
            (kinds.count("reverted") >= 2, f"expected 2 reverted changes (tmp.txt, app.py): {kinds.count('reverted')}"),
        ]
        ok = True
        for cond, msg in checks:
            print(("PASS " if cond else "FAIL ") + msg)
            ok &= cond
        subprocess.run([sys.executable, FLIGHTREC, "timeline", "--project", proj], env=env)
        if keep:
            print("test project:", proj)
        sys.exit(0 if ok else 1)
    finally:
        if not keep:
            shutil.rmtree(proj, ignore_errors=True)


if __name__ == "__main__":
    main()
