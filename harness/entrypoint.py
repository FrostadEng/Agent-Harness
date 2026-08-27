#!/usr/bin/env python3
"""Unprivileged container entrypoint; it owns neither Git nor verification."""
import subprocess, sys
if len(sys.argv)>1 and sys.argv[1]=="proxy":
    from egress_proxy import serve
    serve(); raise SystemExit
if len(sys.argv)<3 or sys.argv[1]!="agent" or sys.argv[2]!="--task": raise SystemExit("usage: agent --task TEXT")
task=sys.argv[3]
p=subprocess.run(["codex","exec","--ask-for-approval","never","--skip-git-repo-check","-C","/workspace","-"],input=task,text=True)
raise SystemExit(p.returncode)
