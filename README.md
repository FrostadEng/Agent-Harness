# Portable Codex Harness

A small trusted controller that gives one Codex container writable task files, but
not Git metadata, publication credentials, project secrets, host files, Docker, or
direct Internet access. Git remains source-control authority; this is deliberately
not a task database, multi-agent framework, memory system, or language toolchain.

## Authority model

The host launcher records the exact base, creates one branch with `git worktree`,
and temporarily hides the linked worktree's `.git` pointer while the agent runs.
The container has a read-only root, dropped capabilities, `no-new-privileges`,
bounded resources, explicit tmpfs paths, and only the task worktree and staged-auth mounts.
It receives a temporary ChatGPT-account-authenticated Codex home at runtime but no
GitHub/project credentials. Codex control-plane authentication is runtime identity,
not a project secret; workload secrets remain unavailable by default.

The agent joins a Docker `--internal` network, which has no direct external route.
A separate dual-homed CONNECT proxy allowlists only the `chatgpt.com` and
`openai.com` suffixes used by the documented current ChatGPT/Codex control plane.
Denied hostnames are logged during real acceptance so the list can be adjusted from
observed traffic rather than silently widened. Repository workload egress is denied in v1. Setting proxy variables
is therefore not the boundary: the internal network is. Verification, diff
accounting, commit creation, and receipts execute on the trusted host after the
container exits. Push and PR publication are reserved controller extensions;
merge is never an agent capability.

## Run

Requirements are Git, Docker, Codex CLI 0.150-compatible behavior, and an existing
host session authenticated by running `codex login` with a ChatGPT account. API keys
are neither read nor accepted by the canonical launcher.

```sh
bin/agent-harness --repo /path/to/project --task 'Fix the greeting' \
  --branch agent-harness/fix-greeting --output /tmp/harness-run
```

The launcher checks `codex login status`, requires ChatGPT authentication, and stages
only file-backed `CODEX_HOME/auth.json` plus a generated minimal configuration in a
mode-0700 per-run directory. It validates that staged home with the installed CLI,
mounts it read/write for token refresh, and destroys it in cleanup. If the host uses
the OS keyring, run `codex -c cli_auth_credentials_store=file login` once. It never
mounts the host home or copies unrelated Codex configuration. There is no agent-writable
receipt/output mount; the trusted launcher records container execution itself. The generated Codex
permission profile also denies sandboxed project commands read access to the staged
control-plane home while allowing the parent Codex runtime to refresh it.

The output retains `worktree/` and `receipt.json`. Authentication and prompt text
are absent from receipts (only a prompt SHA-256 is retained). The receipt marks
`acceptance_evidence` true only when a real container started and Codex executed.
The hidden mock seam is named `--test-agent-command`, emits `mock (TEST_ONLY)`, and
can never produce acceptance evidence.

## Repository contract

Consumers commit `.agent-harness.toml`:

```toml
[verification]
fast = ["make test-unit"]
terminal = ["git diff --check", "make test"]

[policy]
network = "DENY"
push = "REQUIRE_HUMAN"

[budget]
wall_seconds = 900
max_model_turns = 1
max_product_commits = 1
max_changed_files = 10
max_diff_lines = 500
```

Gate commands are repository-owned and run literally in order. The generic
harness contains no Ruff, Tach, pytest, Python, or shell-project assumptions.
Unknown policy actions deny. The classifier guides trusted controller actions;
container topology—not voluntary classifier use—denies agent authority.

Wall time, changed files, additions/deletions, and commits are computed externally.
Hard run/commit exhaustion emits `STOP_BUDGET_EXCEEDED`; diff growth emits
`REQUIRE_HUMAN_SCOPE_ESCALATION`. Codex cannot waive either result.

## PR #2 substrate disposition

| Component | Disposition | Reason |
|---|---|---|
| Dockerfile / Codex image | **REPAIR** | Retained minimal base; now unprivileged with a dedicated entrypoint. |
| `bin/agent-harness` | **REPAIR** | Retained literal launcher; now owns worktree, topology, image identity, and cleanup. |
| `harness/controller.py` | **REPAIR** | Retained config/gate/receipt substrate; agent execution moved outside trusted finalization. |
| `.agent-harness.toml` | **KEEP** | Verification/policy/budget vocabulary remains repository-local. |
| Both fixtures | **KEEP** | Still demonstrate unrelated, repository-defined gates. |
| `tests/mock_agent.py` | **TEST_ONLY** | Unit seam only and receipt-ineligible for acceptance. |
| Receipt contract | **REPAIR** | Adds real-container/Codex evidence, exact image identity, and product SHA. |
| Policy contract | **REPAIR** | Controller decisions retained; denied authority is now mechanically absent. |
| Budget contract | **REPAIR** | Trusted host measures scope, time, and commits. |
| PR #2 components removed | **REMOVE: none** | No working substrate required wholesale replacement. |

## Trusted Docker acceptance

The API-key GitHub Actions workflow was removed: it is not authoritative for v1.
On a trusted Docker-capable host whose Codex CLI is already signed into ChatGPT, run:

```sh
bin/trusted-host-acceptance --output /tmp/agent-harness-acceptance
```

This single command records the exact candidate SHA, builds its image, checks image
layers/files for auth state, runs mechanical adversaries, runs real Codex against
both fixtures, verifies receipt fields, and verifies per-run auth cleanup. The host
must retain the output directory as acceptance evidence. It prints the readiness
terminal only after both real runs pass; its existence alone is not acceptance.

### Observed Codex 0.150 authentication contract

Mechanical inspection on 2026-08-27 found `codex-cli 0.150.0`; `codex login` defaults
to browser-based ChatGPT sign-in, `codex login --device-auth` supports headless login,
and `codex login status` reports the active method. `CODEX_HOME` is supported and must
already exist. Current official Codex documentation defines file-backed credentials
as `CODEX_HOME/auth.json`, permits refresh writes, and warns that the file contains
access tokens. The harness checks the installed CLI's status both before and after
staging rather than inferring authentication from file presence.

Development checks:

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile harness/*.py bin/agent-harness
docker build -t agent-harness:test .
```
