#!/usr/bin/env python3
"""Trusted post-agent controller: gates, budgets, commit, and receipt (stdlib only)."""
import argparse, datetime, hashlib, json, os, pathlib, subprocess, sys, time, tomllib
VERSION="0.2.0"
ACTIONS={"read":"ALLOW","edit":"ALLOW","commit":"ALLOW","push":"REQUIRE_HUMAN","force_push":"DENY",
 "merge":"DENY","destructive_git":"DENY","outside_workspace":"DENY","network":"DENY","secret":"REQUIRE_HUMAN"}
def git(repo,*args): return subprocess.check_output(["git","-C",str(repo),*args],text=True).strip()
def load(repo):
    data=tomllib.loads((repo/".agent-harness.toml").read_text())
    if set(data)-{"verification","policy","budget"}: raise SystemExit("unknown configuration section")
    return data
def policy(cfg,action):
    value=cfg.get("policy",{}).get(action,ACTIONS.get(action,"DENY"))
    if value not in ("ALLOW","DENY","REQUIRE_HUMAN"): raise SystemExit(f"invalid policy decision for {action}")
    return value
def gate(command,cwd,timeout):
    started=time.monotonic()
    try: p=subprocess.run(command,cwd=cwd,shell=True,text=True,capture_output=True,timeout=timeout,executable="/bin/sh")
    except subprocess.TimeoutExpired: return {"command":command,"exit_code":124,"timed_out":True,"duration_seconds":round(time.monotonic()-started,3)}
    if p.stdout: sys.stderr.write(p.stdout)
    if p.stderr: sys.stderr.write(p.stderr)
    return {"command":command,"exit_code":p.returncode,"duration_seconds":round(time.monotonic()-started,3)}
def changes(repo,base):
    subprocess.run(["git","-C",str(repo),"add","-N","--","."],check=True,capture_output=True)
    files=[x for x in git(repo,"diff","--name-only",base,"--").splitlines() if x]; adds=dels=0
    for line in git(repo,"diff","--numstat",base,"--").splitlines():
        a,d,*_=line.split("\t"); adds+=int(a) if a.isdigit() else 0; dels+=int(d) if d.isdigit() else 0
    return files,adds,dels
def main():
    p=argparse.ArgumentParser(); p.add_argument("--repo",required=True); p.add_argument("--receipt",required=True)
    p.add_argument("--task",required=True); p.add_argument("--base"); p.add_argument("--branch"); p.add_argument("--agent-result")
    p.add_argument("--image"); p.add_argument("--image-digest"); p.add_argument("--test-agent-command",help=argparse.SUPPRESS)
    p.add_argument("--policy-check",choices=sorted(ACTIONS)); a=p.parse_args(); repo=pathlib.Path(a.repo).resolve(); cfg=load(repo)
    if a.policy_check:
        d=policy(cfg,a.policy_check); print(d); return {"ALLOW":0,"DENY":2,"REQUIRE_HUMAN":3}[d]
    started=time.monotonic(); start=datetime.datetime.now(datetime.timezone.utc); base=a.base or git(repo,"rev-parse","HEAD")
    branch=a.branch or git(repo,"branch","--show-current"); budget=cfg.get("budget",{}); wall=int(budget.get("wall_seconds",1800))
    test_only=bool(a.test_agent_command); agent={"exit_code":0,"container_started":False,"codex_executed":False}
    if test_only:
        r=gate(a.test_agent_command,repo,wall); agent.update(r)
    elif a.agent_result: agent.update(json.loads(pathlib.Path(a.agent_result).read_text()))
    else: raise SystemExit("agent result is required")
    status="SUCCESS" if agent.get("exit_code")==0 else "AGENT_FAILED"; gates=[]
    if int(budget.get("max_model_turns",1))<1: status="STOP_BUDGET_EXCEEDED"
    if time.monotonic()-started+float(agent.get("duration_seconds",0))>wall: status="STOP_BUDGET_EXCEEDED"
    if status=="SUCCESS":
        for phase in ("fast","terminal"):
            for cmd in cfg.get("verification",{}).get(phase,[]):
                r=gate(cmd,repo,max(1,wall-int(time.monotonic()-started))); r["phase"]=phase; gates.append(r)
                if r["exit_code"]: status="GATE_FAILED"; break
            if status!="SUCCESS": break
    files,adds,dels=changes(repo,base)
    if len(files)>int(budget.get("max_changed_files",50)) or adds+dels>int(budget.get("max_diff_lines",2000)): status="REQUIRE_HUMAN_SCOPE_ESCALATION"
    existing=[x for x in git(repo,"rev-list","--reverse",f"{base}..HEAD").splitlines() if x]
    if len(existing)>int(budget.get("max_product_commits",1)): status="STOP_BUDGET_EXCEEDED"
    commits=[]
    if status=="SUCCESS" and git(repo,"status","--porcelain"):
        if policy(cfg,"commit")!="ALLOW": status="POLICY_DENIED"
        else:
            subprocess.run(["git","-C",str(repo),"add","-A"],check=True)
            subprocess.run(["git","-C",str(repo),"-c","user.name=Agent Harness","-c","user.email=harness@local","commit","-m","agent: complete task"],check=True,capture_output=True)
            commits=[git(repo,"rev-parse","HEAD")]
    end=datetime.datetime.now(datetime.timezone.utc)
    receipt={"schema_version":1,"acceptance_evidence":not test_only and bool(agent.get("container_started")) and bool(agent.get("codex_executed")),
      "harness":{"version":VERSION,"commit":os.getenv("HARNESS_COMMIT")},"target":{"identity":str(repo),"base_commit":base},
      "worktree":{"path":str(repo),"branch":branch},"task":{"prompt_sha256":hashlib.sha256(a.task.encode()).hexdigest()},
      "container":{"image":a.image,"digest":a.image_digest,"started":bool(agent.get("container_started"))},
      "agent":{"name":"mock (TEST_ONLY)" if test_only else "codex","executed":bool(agent.get("codex_executed")),
               "authentication_mode":agent.get("authentication_mode") if not test_only else None},
      "started_at":start.isoformat(),"ended_at":end.isoformat(),"wall_seconds":round(time.monotonic()-started+float(agent.get("duration_seconds",0)),3),
      "agent_runs":[agent],"gates":gates,"policy_events":[{"action":x,"decision":policy(cfg,x)} for x in ACTIONS if policy(cfg,x)!="ALLOW"],
      "budget":{"limits":budget,"consumed":{"model_turns":1,"commits":len(commits),"changed_files":len(files),"additions":adds,"deletions":dels}},
      "result":{"commits":commits,"product_sha":commits[-1] if commits else None,"changed_files":files,"diff":{"additions":adds,"deletions":dels},"status":status}}
    out=pathlib.Path(a.receipt); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps({"status":status,"receipt":str(out)})); return 0 if status=="SUCCESS" else 1
if __name__=="__main__": sys.exit(main())
