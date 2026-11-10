---
name: update-version-matrix
description: Bump the image, tool and package pins flagged by the `check-version-matrix` job, regenerate docs/version-matrix.md and open a PR. Use when given a check-version-matrix job URL, or asked to "bump the versions" / "update the version matrix". Also run unattended by .github/workflows/bump-version-matrix.yml.
---

# Update the version matrix

Pins live in four places:

- images: `_DEFAULT_IMAGES` in `src/package_io/registry.star`;
- L1 clients: the ethereum-package participant of `.github/tests/custom.yaml`;
- CI tools: `mise.toml`, and foundry in `.github/workflows/actions/setup-environment/action.yaml`;
- Kurtosis packages: the `replace` block of `kurtosis.yml`.

`scripts/version-matrix/README.md` is the source of truth for how the scripts work.

## 1. Read the drift

From a job URL:

```bash
gh run view <run> --log --job <job> | grep -E '\s[-+]\|' | sed 's/.*Z //'
```

Otherwise regenerate (step 3) on a fresh `origin/main` and read
`git diff docs/version-matrix.md`. The `+` rows are the new matrix. Keep only
rows marked 🚨 (behind). Skip:

- 📌 `pinned` rows: deliberate holds declared in `PINNED_VERSIONS` in
  `extract-versions.py`, or a release whose image is not published yet.
- Pre-releases (`rc`, `beta`, `alpha`, `dev`): flag them instead.
- Major version jumps of a client (op-nethermind 1.x → 2.x, blockscout): bump
  only if the release notes show no breaking change in the flags or config the
  package passes; otherwise skip them as `other` and say why.
- The hard forks page: forks are not versions and never use 🚨. A bump can
  change it (a newer op-node or op-deployer knows or schedules another fork):
  keep that in the regenerated page and mention it in the PR body, but never
  edit fork settings to make a row green.

Before bumping an image, check it is published:
`docker manifest inspect <image>:<tag>`. The matrix already does this for the
tag it expects, but a multi-arch image can be published one platform at a time.

op-deployer is special: the package runs a `-cdk` build of a fork of the
monorepo, carrying the `--predeployed-file` patch (see `FORK.md`). Bump it only
to a `v<version>-cdk` tag that exists in
`europe-west2-docker.pkg.dev/prj-polygonlabs-devtools-dev/public/op-deployer`;
otherwise skip it as `unpublished`.

## 2. Bump

- Replace the **full image reference**
  (`us-docker.pkg.dev/oplabs-tools-artifacts/images/op-reth:v2.8.1` → `…:v2.8.2`),
  not the bare version: `2.8.1` can match unrelated things.
- Grep the repo for the old reference and update every copy: the unit tests
  under `test/` assert the default images, and `README.md` quotes some of them.
  The matrix only reads `registry.star`, so stale copies elsewhere are caught by
  `kurtosis-test .` at best.
- A `kurtosis.yml` package bump is a full commit SHA plus a `# <date>` comment;
  then run `python3 scripts/version-matrix/verify-package-pins.py`. A
  head-tracked package (`Latest stable version` reads `HEAD (<sha>)`) is bumped
  to the full SHA in that cell's `tree/<sha>` link.
- A `mise.toml` tool keeps its spelling (`v0.0.9` → `v0.0.10`, `1.22.2` → `1.22.3`).

## 3. Regenerate

```bash
GITHUB_TOKEN="${GITHUB_TOKEN:-$(gh auth token)}" python3 scripts/version-matrix/extract-versions.py
python3 scripts/version-matrix/generate-markdown.py
git diff --stat
```

In CI, `GITHUB_TOKEN` is already set: run both scripts without the prefix.

`matrix.json` is gitignored: don't force-add it. Check the bumped rows are now ✅
and nothing else flipped. If another dependency drifted since the nightly, bump
it too rather than leaving a 🚨 row.

## 4. Checks

- `kurtosis lint .` and `kurtosis-test .` when a `.star` file changed.
- Locally, also `rumdl check docs`. The PR's CI deploys devnets.

## 5. Open the PR

Title: `chore: bump <dep> to <version>`, or `chore: bump <dep>, <dep> and <dep>`.
There is no PR template: the body is at most 5 bullets, one per bump
`old → [new](release url)`, plus what was skipped and why (📌, rc, unpublished
image, major version).

**Local**: work in a worktree off `origin/main`, commit, push, `gh pr create`.

**CI** (run by `bump-version-matrix.yml`): only edit files. Do not commit, push
or open the PR: return the title and body, and the workflow opens or refreshes the
PR. Files under `.github/workflows/` are dropped from that PR (the app token
cannot push them), such as the foundry pin in the setup-environment action.
Still edit them, but never claim them in
the body; add a bullet asking a maintainer to apply the exact line by hand. If
nothing is left to bump (every drifted row is 📌, rc or unpublished), make no
change and return an empty title. Either way, list every drifted row in
`bumped` (component, old and new version) or `skipped` (component, current and
latest version, reason: `pinned` for 📌, `pre-release` for rc, `unpublished`, or
`other`): the workflow writes both to the run summary.
