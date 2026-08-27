import json, pathlib, shutil, subprocess, sys, tempfile, unittest

ROOT=pathlib.Path(__file__).parents[1]
CONTROLLER=ROOT/"harness/controller.py"

def fixture(name):
    td=tempfile.TemporaryDirectory(); repo=pathlib.Path(td.name)/"repo"
    shutil.copytree(ROOT/"fixtures"/name,repo)
    subprocess.run(["git","init","-q","-b","main"],cwd=repo,check=True)
    subprocess.run(["git","add","."],cwd=repo,check=True)
    subprocess.run(["git","-c","user.name=Fixture","-c","user.email=f@local","commit","-qm","fixture"],cwd=repo,check=True)
    return td,repo

class HarnessTest(unittest.TestCase):
    def test_both_project_configs_drive_successful_run(self):
        for name in ("python-repo","shell-repo"):
            with self.subTest(name=name):
                td,repo=fixture(name); self.addCleanup(td.cleanup); receipt=repo/"receipt.json"
                p=subprocess.run([sys.executable,CONTROLLER,"--repo",repo,"--receipt",receipt,"--task","fix defect",
                    "--agent-command",f"{sys.executable} {ROOT/'tests/mock_agent.py'}"],text=True,capture_output=True)
                self.assertEqual(p.returncode,0,p.stderr+p.stdout)
                data=json.loads(receipt.read_text()); self.assertEqual(data["result"]["status"],"SUCCESS")
                self.assertEqual([g["phase"] for g in data["gates"]],["fast","terminal","terminal"])
                self.assertEqual(len(data["result"]["commits"]),1)

    def test_policy_is_fail_closed_and_tristate(self):
        td,repo=fixture("shell-repo"); self.addCleanup(td.cleanup)
        for action,code,text in (("force_push",2,"DENY"),("push",3,"REQUIRE_HUMAN"),("read",0,"ALLOW")):
            p=subprocess.run([sys.executable,CONTROLLER,"--repo",repo,"--policy-check",action],text=True,capture_output=True)
            self.assertEqual((p.returncode,p.stdout.strip()),(code,text))

    def test_turn_budget_stops_before_agent(self):
        td,repo=fixture("shell-repo"); self.addCleanup(td.cleanup)
        config=(repo/".agent-harness.toml").read_text().replace("max_model_turns = 1","max_model_turns = 0")
        (repo/".agent-harness.toml").write_text(config); receipt=repo/"receipt.json"
        p=subprocess.run([sys.executable,CONTROLLER,"--repo",repo,"--receipt",receipt,"--task","never run",
                          "--agent-command","touch SHOULD_NOT_EXIST"],capture_output=True)
        self.assertNotEqual(p.returncode,0); self.assertFalse((repo/"SHOULD_NOT_EXIST").exists())
        self.assertEqual(json.loads(receipt.read_text())["result"]["status"],"STOP_BUDGET_EXCEEDED")

    def test_scope_escalation(self):
        td,repo=fixture("shell-repo"); self.addCleanup(td.cleanup); receipt=repo/"receipt.json"
        p=subprocess.run([sys.executable,CONTROLLER,"--repo",repo,"--receipt",receipt,"--task","expand",
          "--agent-command","sed -i s/goodbye/hello/ greet.sh; printf x > one; printf x > two; printf x > three"],capture_output=True)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(json.loads(receipt.read_text())["result"]["status"],"REQUIRE_HUMAN_SCOPE_ESCALATION")

if __name__ == "__main__": unittest.main()
