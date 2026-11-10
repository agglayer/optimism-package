# Version matrix system

Tracks whether the versions this package deploys are still current, and surfaces
the answer as documentation instead of a thing someone has to remember to check.

Four kinds of dependency are covered:

- **Container images**: the `_DEFAULT_IMAGES` of `src/package_io/registry.star`
  that kurtosis-cdk deploys through this package.
- **L1 clients**: the ethereum-package participant of `.github/tests/custom.yaml`.
  The package itself launches the L1 with the ethereum-package default images.
- **CI tools**: `mise.toml`, plus foundry in
  `.github/workflows/actions/setup-environment/action.yaml`.
- **External Kurtosis packages**: the `replace` block of `kurtosis.yml`.

All are compared against their upstream GitHub releases and annotated with a
status. The output lands in [`docs/version-matrix.md`](../../docs/version-matrix.md).
The [hard forks](#hard-forks) the devnet activates get their own page,
[`docs/hard-forks.md`](../../docs/hard-forks.md).

## Components

| Script                   | Role                                                                                         | Needs a token |
| ------------------------ | -------------------------------------------------------------------------------------------- | ------------- |
| `extract-versions.py`    | Reads `registry.star`, `kurtosis.yml`, `mise.toml` and the CI configs, writes `matrix.json`  | yes           |
| `hard_forks.py`          | Imported by `extract-versions.py`: reads fork schedules and pinned client sources            | yes           |
| `generate-markdown.py`   | Renders `matrix.json` into the docs pages                                                    | no            |
| `verify-package-pins.py` | Checks the `replace` block is the single source of truth for package versions                | no            |

```text
registry.star ───┐
custom.yaml ─────┤
mise.toml ───────┼─► extract-versions.py ──► matrix.json ──► generate-markdown.py ──► version-matrix.md + hard-forks.md
kurtosis.yml ────┤
GitHub API ──────┤
registries ──────┘
```

## Usage

```bash
pip install -r scripts/version-matrix/requirements.txt
export GITHUB_TOKEN="..."   # or: export GITHUB_TOKEN="$(gh auth token)"

python3 scripts/version-matrix/extract-versions.py    # writes matrix.json
python3 scripts/version-matrix/generate-markdown.py   # writes the docs pages
```

`generate-markdown.py` shells out to `rumdl fmt` to align the tables it writes,
because the docs are linted with MD060 (aligned tables) and the status emojis do
not all have the same display width. `rumdl` is pinned in `requirements.txt`,
which `checks.yaml` installs to lint the docs; if it is missing the script still
writes the pages, warns, and leaves the tables unaligned.

`verify-package-pins.py` runs offline and needs no token:

```bash
python3 scripts/version-matrix/verify-package-pins.py
```

## CI

- `checks.yaml` runs `verify-package-pins.py` and lints the docs on every PR.
- `nightly.yml` runs the `check-version-matrix` job. It regenerates the matrix
  and fails if the committed pages are out of date, which is the signal that a
  dependency has moved.
- `bump-version-matrix.yml` runs after it: Claude follows
  `.claude/skills/update-version-matrix/SKILL.md` to bump what is behind, and the
  workflow opens or refreshes a PR. Merging stays manual.

Regenerate and commit the docs pages when bumping a dependency, so the nightly
diff stays empty. `matrix.json` is gitignored.

## Status system

| Status     | Icon | Description                                                     |
| ---------- | ---- | --------------------------------------------------------------- |
| up to date | ✅   | Running the latest upstream release                             |
| ahead      | ⚡️   | Ahead of the latest release: a prerelease or a patched build    |
| behind     | 🚨   | An upstream release is available and should be picked up        |
| pinned     | 📌   | Deliberately held back, or its image is not published yet       |

An image behind its upstream release is checked against its registry first: if
the image for the new release is not published yet (same `v` prefix and build
variant suffix, such as op-deployer's `-cdk`), the row reads `📌 pinned — No
<tag> image published yet.` so the bump workflow does not pick up a release that
would break the devnet. The check reads the registry anonymously; if it cannot
answer, the row stays 🚨.

## Hard forks

`hard_forks.py` compares what the devnet activates with what the pinned clients
support:

| Domain   | Devnet schedule                                                                              | Checked against                                                              |
| -------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| L1       | ethereum-package `minimal` preset defaults, overridden in `.github/tests/custom.yaml`        | geth `params/config.go`, lighthouse built-in mainnet `config.yaml`           |
| OP Stack | the `<fork>_time_offset` defaults of `_DEFAULT_NETWORK_PARAMS` in `src/l2/input_parser.star` | op-node `op-core/forks/forks.go`, the superchain registry op-deployer embeds |

Upstream files are read at the refs this repo pins (image tags, the `kurtosis.yml`
ethereum-package commit, the superchain-registry submodule of the monorepo at the
op-deployer tag), never at upstream HEAD. A fork that is merely announced
upstream therefore never makes the nightly diff non-empty. op-deployer activates
at genesis every fork up to the latest one OP Mainnet has scheduled in that
registry, so a knob left unset reads `✅ enabled — op-deployer default`. A failed
fetch fails the script instead of rendering a fork as unsupported.

| Status                  | Icon | Description                                                       |
| ----------------------- | ---- | ----------------------------------------------------------------- |
| enabled                 | ✅   | Activated by the devnet and known to the pinned clients           |
| not enabled             | 💤   | Known to the pinned clients, but the devnet leaves it off         |
| not supported yet       | ⏳   | Exposed by the package, but not known to a pinned client yet      |
| enabled but unsupported | ❌   | Configured by the devnet, but a pinned client ignores the setting |

Fork rows never use 🚨, so the bump workflow leaves them alone: enabling a fork
is a decision, not a version bump. The L1 code is shared with the copies of
`hard_forks.py` in kurtosis-pos and kurtosis-cdk: keep them in sync. A new L1
fork needs its EL name in `L1_EL_FORKS`, or its geth column reads `—`.

## Adding an image

Every image in `_DEFAULT_IMAGES` must be listed in exactly one of two tables in
`extract-versions.py`, otherwise the script exits non-zero and names it. That is
deliberate: a new image should not be able to slip in untracked.

- `COMPONENT_REPOS`: an image kurtosis-cdk deploys through this package, the
  only ones kept up to date. Maps the registry ID to `(org/repo, tag prefix)`.
  Monorepo prefixes such as `op-node/v` are resolved from the repo's tag refs,
  the highest stable one winning; `v` and `""` use the latest release, falling
  back to tags.
- `SKIPPED_IMAGES`: every other image, with the reason. They are listed on the
  page as "Not tracked".

## Pinned versions

Some components cannot track the latest release yet. Without a rule for this,
those rows show 🚨 permanently, which trains everyone to ignore the alarm and
hides real regressions.

Declare such cases in `PINNED_VERSIONS`, keyed by the registry ID, with a short
reason:

```python
PINNED_VERSIONS = {
    "op-reth": "Only supports op-reth 2.8.x so far.",
}
```

Keep every reason in the same short form, `Only supports <component> <line> so
far.`, so the status column reads consistently and stays narrow.

The pin only ever downgrades a `behind` result. Once the pinned component
catches up with (or overtakes) stable, its real status is reported again: that
is the signal to delete the entry.

## External Kurtosis packages

Package versions live in exactly one place: the `replace` block of
`kurtosis.yml`. `replace` overrides the version of every matching reference in
the repo, including transitive dependencies, so the `.star` files reference
packages *without* an `@<version>` suffix and a bump only happens once.

```yaml
replace:
  github.com/ethpandaops/ethereum-package: github.com/ethpandaops/ethereum-package@<commit> # <date>
```

`verify-package-pins.py` fails if:

- a `.star` file pins a version inline: `replace` silently overrides it, so the
  inline version is misleading rather than effective;
- a referenced package has no `replace` entry, or an entry without a version:
  both resolve at upstream HEAD;
- a `replace` entry is no longer referenced anywhere: stale config.

The Grafana dashboard sources in `src/package_io/input_parser.star` are GitHub
locators too, but not Kurtosis packages: they are listed in `NOT_PACKAGES`.

A **tag** pin (`@v2.0.0`) is release-tracked: compared against the latest
release or tag. A **commit** pin (`@6dd3f26…`) is head-tracked: compared against
the default branch tip, labelled `HEAD (<sha>)`, and reported `🚨 behind` with
its commit distance as soon as HEAD moves past it. Packages deliberately held
back go in `PINNED_PACKAGES`, keyed by package locator.
