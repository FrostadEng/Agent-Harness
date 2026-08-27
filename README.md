# Portable Codex Harness

A deliberately small, single-agent walking skeleton: clone a Git repository into an isolated working tree, run one bounded Codex invocation in Docker, execute that repository's checks, commit a successful result, and emit JSON evidence. Git is the source-control authority and GitHub issues/PRs remain the work-state authority. There is no task database.

It is **not** a multi-agent orchestrator, memory/semantic-graph product, autonomous review loop, or project-specific framework. Docker is the only v1 isolation backend.

## Run it

Requirements are Git, Docker, and an `OPENAI_API_KEY` or `CODEX_API_KEY` in the environment. Credentials are passed at runtime and are neither copied into the image nor included in receipts.

```sh
bin/agent-harness --repo /path/to/project --task 'Fix the failing greeting' \
  --branch agent-harness/fix-greeting --output /tmp/harness-run
```

The launcher builds `Dockerfile`, clones the target (without modifying the source checkout), creates the requested branch, mounts that working tree at `/workspace`, and writes `/tmp/harness-run/receipt.json`. The completed checkout remains at `/tmp/harness-run/worktree`, ready for normal inspection and push/PR creation. The harness never merges.

## Repository contract

Consumers commit `.agent-harness.toml`:

```toml
[verification]
fast = ["git diff --check", "make test-unit"]
terminal = ["make test"]

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

Commands run literally, in order, with exact exit code and duration recorded. Output is forwarded to the run log but deliberately omitted from the receipt, where it might expose secrets. A nonzero gate cannot be reinterpreted. Fast checks run after the single agent turn; terminal checks run only if fast checks pass. Project bootstrap and toolchains belong to the consumer, not the generic image.

## Policy, budget, and trust

The controller's explicit actions return `ALLOW`, `DENY`, or `REQUIRE_HUMAN`; unknown actions fail closed. Defaults deny force-push, merge, destructive Git, out-of-workspace commands and network, and require a human for push and secrets. `codex exec --sandbox workspace-write` mechanically confines the agent invocation to the mounted worktree; Docker receives no network entitlement from repository configuration. The launcher exposes no host workspace beyond the isolated checkout and receipt directory.

Wall time is enforced as a subprocess timeout. Model turns and commits are capped, and changed-file/diff-line growth becomes `REQUIRE_HUMAN_SCOPE_ESCALATION`; the agent cannot waive these values. Receipt terminal states make stops explicit. No transcript, prompt, or command output is retained—only a SHA-256 prompt digest and command result metadata.

The receipt also identifies the version, repository/base/branch, timestamps, image metadata when supplied, agent, commits, diff stat, gates, policy decisions, budget use, and terminal status.

## Adopting and extending

Copy the TOML contract into any Git repository and choose commands its own environment supports. `fixtures/python-repo` and the unrelated POSIX-shell `fixtures/shell-repo` demonstrate that no Python/Atlas verification is built into the controller.

A future agent backend replaces only the one `codex exec` subprocess. A future isolation backend replaces the launcher's Docker invocation. Neither change requires a new work-state store, policy vocabulary, verification file, or receipt contract. Independent review may later attach at the terminal boundary, but must be explicitly bounded by acceptance criteria and threat model; it may not expand scope indefinitely.

## Development checks

```sh
python3 -m unittest discover -s tests -v
docker build -t agent-harness:test .
```
