# FORK

## Upstream

- Repository: <https://github.com/ethpandaops/optimism-package>
- Base: `upstream/main`
- Current sync point: [7bef190](https://github.com/ethpandaops/optimism-package/commit/7bef190d7c0b9f619438ed08b17bd5e5f51e72ff)

## Policy

- [`main`](https://github.com/agglayer/optimism-package/tree/main): Tracks `upstream/main` exactly, without modifications.
- [`overlay/main`](https://github.com/agglayer/optimism-package/tree/overlay/main): Contains our patch stack on top of `upstream/main` — this is where all fork-specific changes live.

## Patch Stack

- All fork-only changes live as a patch stack (linear, reviewed).
- Patches are ordered from the most recent to the least recent.

| # | Title | Scope | Notes |
|---|-------|-------|-------|
| 19 | chore: bump op-stack versions and switch default EL to op-reth | el/cl clients, op components | Bump the OP stack to the latest stable releases and default new participants to op-reth, as op-geth has reached [end of support](https://docs.optimism.io/notices/op-geth-deprecation) and the Karst hardfork requires op-reth |
| 18 | chore: bump versions and switch to op-reth in custom.yaml | el clients, ci | Bump versions and switch to op-reth in custom.yaml |
| 17 | chore: bump kurtosis and op components versions | ci | Bump kurtosis and op components versions |
| 16 | chore: bump op-deployer to v5 | op-deployer | Bump op-deployer and contracts to v5 |
| 15 | fix: op-node l1 genesis logic and bump custom configs | ci | Fix op-node L1 genesis logic and bump custom configs |
| 14 | fix: enable cell proofs on op-batcher | fusaka hf | Enable cell proofs on op-batcher for fusaka hardfork |
| 13 | fix: typo in op-node version check and add antithesis-like test config | op-node, ci, antithesis | Fix typo |
| 12 | fix: op-node version check to allow custom build | op-node | Fix op-node version check to allow custom builds based on v1.14.1 |
| 11 | fix: enable block finalization for fusaka env | ci, fusaka hf | Enable block finalization for fusaka environment and add additional checks in ci to ensure safe and finalized blocks are progressing |
| 10 | feat: upgrade contracts and tooling, fix service naming and metric, support for fusaka hf | contracts, op-deployer, el/cl clients, op-batcher, op-proposer, proxyd, tests, ci, fusaka hf | Upgrade op-deployer and contract versions, fix service naming (el/cl clients, op-batcher, op-proposer and proxyd), disable metrics registration, and add support and test configs for Fusaka hardfork |
| 09 | docs: document patches | docs | Add `FORK.md` to track fork policy and patches |
| 08 | revert: el/cl client naming | el/cl clients | Revert client renaming to avoid updating references across [kurtosis-cdk](https://github.com/0xPolygon/kurtosis-cdk), [e2e](https://github.com/agglayer/e2e), and other repositories |
| 07 | fix: ci jobs issues with op-deployer and `predeployed_allocs.json` | op-deployer, ci | Fix default configuration, test configs, and ci workflows related to op-deployer pre-deployed allocs |
| 06 | feat: allow to disable proposer | op-proposer | Add ability to disable the op-proposer component |
| 05 | feat: pre-deployed allocs for deployer | op-deployer | Enable passing predeployed files (e.g. `predeployed-allocs.json`) to the op-deployer (*) |
| 04 | feat(op-batcher): max channel duration | op-batcher | Allow customization of the op-batcher’s maximum channel duration |
| 03 | ci: disable k8s tests | ci | Disable kubernetes tests in ci |
| 02 | ci: run tests when pushing commits to `overlay/main` | ci | Run ci tests when pushing commits to `overlay/main` for validation purposes |
| 01 | chore: update `kurtosis.yml` | kurtosis | Update `kurtosis.yml` to ensure this package is usable |

(*) We also maintain a [fork](https://github.com/leovct/optimism) of the optimism monorepo to add support for predeployed files in the op-deployer. The patch is rebased onto each new op-deployer release as an `op-deployer/<version>-cdk` branch, published to `europe-west2-docker.pkg.dev/prj-polygonlabs-devtools-dev/public/op-deployer`. Note that the `--predeployed-file` flag does not exist upstream, so it must be carried forward on every rebase.
