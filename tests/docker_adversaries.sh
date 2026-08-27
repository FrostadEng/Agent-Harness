#!/bin/sh
set -eu
image=$1; net="ah-adversary-$$"; scratch=$(mktemp -d); trap 'docker network rm "$net" >/dev/null 2>&1 ||:; rm -rf "$scratch"' EXIT
docker network create --internal "$net" >/dev/null
# Root filesystem, host filesystem, Docker authority, secrets, and direct egress are absent.
! docker run --rm --network "$net" --read-only --cap-drop ALL --security-opt no-new-privileges --entrypoint sh "$image" -c 'touch /ESCAPE'
! docker run --rm --network "$net" --read-only --cap-drop ALL --entrypoint sh "$image" -c 'test -S /var/run/docker.sock'
! docker run --rm --network "$net" --read-only --cap-drop ALL --entrypoint sh "$image" -c 'test -n "${PROJECT_DEPLOY_TOKEN:-}"'
! docker run --rm --network "$net" --read-only --cap-drop ALL --entrypoint sh "$image" -c 'test -n "${GITHUB_TOKEN:-}${GH_TOKEN:-}" || test -e "$HOME/.config/gh/hosts.yml"'
! docker run --rm --network "$net" --read-only --cap-drop ALL --entrypoint sh "$image" -c 'git push --force https://github.com/FrostadEng/Agent-Harness HEAD:x'
! docker run --rm --network "$net" --read-only --cap-drop ALL --entrypoint sh "$image" -c 'command -v gh && gh pr merge 1'
! docker run --rm --network "$net" --read-only --cap-drop ALL --entrypoint node "$image" -e 'require("https").get("https://example.com",()=>process.exit(0)).on("error",()=>process.exit(1)); setTimeout(()=>process.exit(2),3000)'
