#!/usr/bin/env python3
"""Literal, single-agent Codex harness controller (stdlib only)."""
import argparse, datetime, hashlib, json, os, pathlib, subprocess, sys, time, tomllib

VERSION = "0.1.0"
ACTIONS = {
    "read": "ALLOW", "edit": "ALLOW", "commit": "ALLOW",
    "push": "REQUIRE_HUMAN", "force_push": "DENY", "merge": "DENY",
    "destructive_git": "DENY", "outside_workspace": "DENY",
    "network": "DENY", "secret": "REQUIRE_HUMAN",
}

def run(cmd, cwd, timeout=None):
    start = time.monotonic()
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=True, text=True, capture_output=True,
                           timeout=timeout, executable="/bin/sh")
        if p.stdout: sys.stderr.write(p.stdout)
        if p.stderr: sys.stderr.write(p.stderr)
        return {"command": cmd, "exit_code": p.returncode,
                "duration_seconds": round(time.monotonic()-start, 3)}
    except subprocess.TimeoutExpired as e:
        return {"command": cmd, "exit_code": 124,
                "duration_seconds": round(time.monotonic()-start, 3),
                "timed_out": True}

def load(repo):
    path = repo / ".agent-harness.toml"
    if not path.is_file(): raise SystemExit("missing .agent-harness.toml")
    data = tomllib.loads(path.read_text())
    allowed = {"verification", "policy", "budget"}
    if set(data) - allowed: raise SystemExit("unknown configuration section")
    return data

def policy(config, action):
    if action not in ACTIONS: return "DENY"
    value = config.get("policy", {}).get(action, ACTIONS[action])
    if value not in ("ALLOW", "DENY", "REQUIRE_HUMAN"):
        raise SystemExit(f"invalid policy decision for {action}")
    return value

def git(repo, args):
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()

def main():
    ap = argparse.ArgumentParser(description="Run one bounded Codex task in a repository")
    ap.add_argument("--repo", default="/workspace")
    ap.add_argument("--receipt", default="/output/receipt.json")
    ap.add_argument("--task", help="task prompt (not retained; only its digest is receipted)")
    ap.add_argument("--task-file")
    ap.add_argument("--agent-command", help=argparse.SUPPRESS)
    ap.add_argument("--policy-check", choices=sorted(ACTIONS))
    args = ap.parse_args()
    repo = pathlib.Path(args.repo).resolve(); cfg = load(repo)
    if args.policy_check:
        decision = policy(cfg, args.policy_check); print(decision)
        return 0 if decision == "ALLOW" else (2 if decision == "DENY" else 3)
    prompt = args.task or (pathlib.Path(args.task_file).read_text() if args.task_file else None)
    if not prompt: ap.error("--task or --task-file is required")
    start_dt = datetime.datetime.now(datetime.timezone.utc); started = time.monotonic()
    base = git(repo, ["rev-parse", "HEAD"]); branch = git(repo, ["branch", "--show-current"])
    budget = cfg.get("budget", {}); wall = int(budget.get("wall_seconds", 1800))
    max_turns = int(budget.get("max_model_turns", 1))
    events=[]; gates=[]; status="SUCCESS"; model_turns=0
    if max_turns < 1: status="STOP_BUDGET_EXCEEDED"
    else:
        model_turns=1
        command = args.agent_command or "codex exec --sandbox workspace-write --skip-git-repo-check -C . -"
        before=time.monotonic()
        try:
            p=subprocess.run(command, cwd=repo, shell=True, text=True, input=prompt,
                             capture_output=True, timeout=max(1, wall), executable="/bin/sh")
            if p.stdout: sys.stderr.write(p.stdout)
            if p.stderr: sys.stderr.write(p.stderr)
            events.append({"command":"codex exec", "exit_code":p.returncode,
                           "duration_seconds":round(time.monotonic()-before,3)})
            if p.returncode: status="AGENT_FAILED"
        except subprocess.TimeoutExpired:
            events.append({"command":"codex exec", "exit_code":124,
                           "duration_seconds":round(time.monotonic()-before,3), "timed_out":True})
            status="STOP_BUDGET_EXCEEDED"
    remaining=max(1, wall-int(time.monotonic()-started))
    if status == "SUCCESS":
        for phase in ("fast", "terminal"):
            for command in cfg.get("verification", {}).get(phase, []):
                result=run(command, repo, remaining); result["phase"]=phase; gates.append(result)
                if result["exit_code"]: status="GATE_FAILED"; break
            if status != "SUCCESS": break
    # Intent-to-add makes untracked scope visible to ordinary diff accounting
    # without staging content or changing the eventual commit semantics.
    subprocess.run(["git","add","-N","--","."],cwd=repo,check=True,capture_output=True)
    changed=git(repo,["diff","--name-only",base,"--"]); files=[x for x in changed.splitlines() if x]
    stat=git(repo,["diff","--numstat",base,"--"])
    additions=deletions=0
    for line in stat.splitlines():
        a,d,*_=line.split("\t"); additions += int(a) if a.isdigit() else 0; deletions += int(d) if d.isdigit() else 0
    max_files=int(budget.get("max_changed_files",50)); max_lines=int(budget.get("max_diff_lines",2000))
    if len(files)>max_files or additions+deletions>max_lines: status="REQUIRE_HUMAN_SCOPE_ESCALATION"
    commits=[]
    if status == "SUCCESS" and git(repo,["status","--porcelain"]):
        if policy(cfg,"commit") != "ALLOW": status="POLICY_DENIED"
        else:
            subprocess.run(["git","add","-A"],cwd=repo,check=True)
            subprocess.run(["git","-c","user.name=Agent Harness","-c","user.email=harness@local",
                            "commit","-m","agent: complete task"],cwd=repo,check=True,capture_output=True)
            commits=[git(repo,["rev-parse","HEAD"])]
    max_commits=int(budget.get("max_product_commits",1))
    if len(git(repo,["rev-list","--reverse",f"{base}..HEAD"]).splitlines())>max_commits: status="STOP_BUDGET_EXCEEDED"
    denied=[{"action":a,"decision":policy(cfg,a)} for a in ACTIONS if policy(cfg,a)!="ALLOW"]
    end=datetime.datetime.now(datetime.timezone.utc)
    receipt={"schema_version":1,"harness":{"version":VERSION,"commit":os.getenv("HARNESS_COMMIT")},
      "target":{"identity":git(repo,["config","--get","remote.origin.url"]) if run("git config --get remote.origin.url",repo)["exit_code"]==0 else str(repo),"base_commit":base},
      "worktree":{"path":str(repo),"branch":branch},"task":{"prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest()},
      "container":{"image":os.getenv("HARNESS_IMAGE"),"digest":os.getenv("HARNESS_IMAGE_DIGEST")},
      "agent":{"name":"codex","model":os.getenv("CODEX_MODEL")},"started_at":start_dt.isoformat(),"ended_at":end.isoformat(),
      "wall_seconds":round(time.monotonic()-started,3),"agent_runs":events,"gates":gates,"policy_events":denied,
      "budget":{"limits":budget,"consumed":{"model_turns":model_turns,"review_cycles":0,"commits":len(commits),"changed_files":len(files),"additions":additions,"deletions":deletions}},
      "result":{"commits":commits,"changed_files":files,"diff":{"additions":additions,"deletions":deletions},"status":status}}
    out=pathlib.Path(args.receipt); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps({"status":status,"receipt":str(out)}))
    return 0 if status=="SUCCESS" else 1

if __name__ == "__main__": sys.exit(main())
