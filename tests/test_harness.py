import json,pathlib,shutil,subprocess,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).parents[1]; CONTROLLER=ROOT/"harness/controller.py"
def fixture(name):
    td=tempfile.TemporaryDirectory(); repo=pathlib.Path(td.name)/"repo"; shutil.copytree(ROOT/"fixtures"/name,repo)
    subprocess.run(["git","init","-q","-b","main"],cwd=repo,check=True); subprocess.run(["git","add","."],cwd=repo,check=True)
    subprocess.run(["git","-c","user.name=Fixture","-c","user.email=f@local","commit","-qm","fixture"],cwd=repo,check=True); return td,repo
class HarnessTest(unittest.TestCase):
 def run_mock(self,name,extra=()):
    td,repo=fixture(name); self.addCleanup(td.cleanup); receipt=repo/"receipt.json"
    cmd=[sys.executable,CONTROLLER,"--repo",repo,"--receipt",receipt,"--task","fix defect","--test-agent-command",f"{sys.executable} {ROOT/'tests/mock_agent.py'}",*extra]
    p=subprocess.run(cmd,text=True,capture_output=True); return p,json.loads(receipt.read_text()),repo
 def test_configs_drive_tests_but_mock_is_never_acceptance(self):
    for name in ("python-repo","shell-repo"):
      with self.subTest(name=name):
       p,d,_=self.run_mock(name); self.assertEqual(p.returncode,0,p.stderr); self.assertEqual(d["result"]["status"],"SUCCESS")
       self.assertFalse(d["acceptance_evidence"]); self.assertEqual(d["agent"]["name"],"mock (TEST_ONLY)")
       self.assertEqual([g["phase"] for g in d["gates"]],["fast","terminal","terminal"])
 def test_scope_escalation_is_external(self):
    td,repo=fixture("shell-repo"); self.addCleanup(td.cleanup); out=repo/"r.json"
    p=subprocess.run([sys.executable,CONTROLLER,"--repo",repo,"--receipt",out,"--task","expand","--test-agent-command","touch one two three"],capture_output=True)
    self.assertNotEqual(p.returncode,0); self.assertEqual(json.loads(out.read_text())["result"]["status"],"REQUIRE_HUMAN_SCOPE_ESCALATION")
 def test_policy_fail_closed(self):
    td,repo=fixture("shell-repo"); self.addCleanup(td.cleanup)
    # Policy inspection remains useful for controller decisions; container tests prove enforcement.
    for action,code in (("force_push",2),("push",3),("read",0)):
      p=subprocess.run([sys.executable,CONTROLLER,"--repo",repo,"--receipt","x","--task","x","--policy-check",action])
      self.assertEqual(p.returncode,code)
if __name__=="__main__": unittest.main()
