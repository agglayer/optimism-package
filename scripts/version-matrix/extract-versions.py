#!/usr/bin/env python3
"""
Automated version matrix extraction tool for the optimism-package.

Extracts version information from:
1. `_DEFAULT_IMAGES` in src/package_io/registry.star — the container images we deploy.
2. The L1 client images pinned in .github/tests/custom.yaml.
3. The CI tools pinned in mise.toml and the setup-environment action.
4. The `replace` block of kurtosis.yml — the external Kurtosis packages we pin.

All are compared against their upstream GitHub releases (or branch HEAD, for
packages that ship faster than they tag) and annotated with a status. Hard fork
schedules are added by hard_forks.py. The result is written to matrix.json,
which generate-markdown.py renders into the docs.
"""

import os
import re
import json
import tomllib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
import yaml

import hard_forks


@dataclass
class ComponentVersion:
    """A container image or tool version we deploy, and how it compares to upstream."""
    version: str
    image: str
    latest_version: Optional[str] = None
    version_source_url: Optional[str] = None
    latest_version_source_url: Optional[str] = None
    status: Optional[str] = None
    pin_reason: Optional[str] = None
    # "l1" or "l2" for images, "tool" for CI tools.
    group: str = "l2"


@dataclass
class PackageVersion:
    """A pinned external Kurtosis package dependency."""
    pin: str
    pin_date: Optional[str] = None
    pin_source_url: Optional[str] = None
    latest_version: Optional[str] = None
    latest_version_date: Optional[str] = None
    latest_version_source_url: Optional[str] = None
    status: Optional[str] = None
    commit_distance: Optional[str] = None
    tracking_mode: str = "release"
    pin_reason: Optional[str] = None
    core: bool = False


OPTIMISM = "ethereum-optimism/optimism"
INFRA = "ethereum-optimism/infra"

# Images from `_DEFAULT_IMAGES` mapped to the GitHub repo that releases them and
# the prefix of its release tags. Keys are the registry IDs (`OP_NODE = "op-node"`).
# Only the images kurtosis-cdk deploys through this package are kept up to date:
# the default EL and CL, the batcher, the proposer, proxyd and the deployer.
# Monorepos tag each component as `<component>/vX.Y.Z`; those prefixes are
# resolved through the tag refs rather than `releases/latest`, which only knows
# the one release the repo marked as latest. An image absent from this table
# must be in SKIPPED_IMAGES, otherwise main() fails.
COMPONENT_REPOS = {
    "op-reth": (OPTIMISM, "op-reth/v"),
    "op-node": (OPTIMISM, "op-node/v"),
    "op-batcher": (OPTIMISM, "op-batcher/v"),
    "op-proposer": (OPTIMISM, "op-proposer/v"),
    "op-deployer": (OPTIMISM, "op-deployer/v"),
    "proxyd": (INFRA, "proxyd/v"),
}

# Images kurtosis-cdk does not deploy through this package, so left out of the
# matrix. Keeping this explicit means a newly added image that lands in neither
# table is a visible gap rather than a silent omission.
SKIPPED_IMAGES = {
    # EL
    "op-geth", "op-erigon", "op-nethermind", "op-besu", "op-rbuilder",
    # CL
    "kona-node", "hildr",
    # OP services
    "op-challenger", "op-conductor", "op-conductor-ops", "op-faucet",
    "op-interop-mon", "op-signer", "op-supervisor", "kona-supervisor",
    "op-test-sequencer", "da-server",
    # sidecars and utils
    "rollup-boost", "flashblocks-websocket-proxy", "flashblocks-rpc",
    "deployment-utils", "openssl", "tx-fuzzer",
    # observability and explorers
    "prometheus", "grafana", "loki", "promtail",
    "op-blockscout", "op-blockscout-verifier",
}

# L1 clients, read from the ethereum-package participant of
# .github/tests/custom.yaml. Keys are participant fields.
L1_IMAGES = {
    "el_image": ("geth", "ethereum/go-ethereum", "v"),
    "cl_image": ("lighthouse", "sigp/lighthouse", "v"),
}

# CI tools pinned in mise.toml, keyed by mise tool name.
MISE_TOOLS = {
    "just": ("just", "casey/just", ""),
    "ubi:kurtosis-tech/kurtosis-cli-release-artifacts[exe=kurtosis]":
        ("kurtosis", "kurtosis-tech/kurtosis", ""),
    "ubi:leovct/kurtosis-test": ("kurtosis-test", "leovct/kurtosis-test", "v"),
    "pipx:ethereum-optimism/kurtosis-lint": ("kurtosis-lint", "ethereum-optimism/kurtosis-lint", "v"),
    "yq": ("yq", "mikefarah/yq", "v"),
}

# Foundry is installed by the setup-environment action, not mise.
SETUP_ACTION = ".github/workflows/actions/setup-environment/action.yaml"

# Components deliberately held back from the latest stable release, keyed by
# registry ID (or tool name). These render as "pinned" instead of "behind" so
# that genuine regressions stay visible in the matrix.
#
# Keep every reason in the same short form: "Only supports <component> <line> so far."
PINNED_VERSIONS: Dict[str, str] = {}

# External Kurtosis packages deliberately held back, keyed by package locator.
# Same convention as PINNED_VERSIONS.
PINNED_PACKAGES: Dict[str, str] = {}

# Packages the devnet cannot run without (the L1); the rest is additional.
# Keys are package locators.
CORE_PACKAGES = {"github.com/ethpandaops/ethereum-package"}

STATUS_MATCHES = "up to date"
STATUS_BEHIND = "behind"
STATUS_NEWER = "ahead"
STATUS_PINNED = "pinned"

PRERELEASE = re.compile(r"-(alpha|beta|rc|test|dev|pr|preview|unstable)|-op-private",
                        re.IGNORECASE)


class VersionMatrixExtractor:
    """Extracts and manages version matrix information."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.registry_path = repo_root / "src" / "package_io" / "registry.star"
        self.kurtosis_yaml_path = repo_root / "kurtosis.yml"
        # Several images share a repo and tag prefix (loki and promtail).
        self._latest: Dict[Tuple[str, str], Optional[str]] = {}

    # --- images ------------------------------------------------------------

    def registry_images(self) -> Dict[str, str]:
        """{registry ID: image} from `_DEFAULT_IMAGES` in registry.star."""
        content = self.registry_path.read_text()
        ids = dict(re.findall(r'^([A-Z][A-Z0-9_]*)\s*=\s*"([^"]+)"', content, re.MULTILINE))
        match = re.search(r"^_DEFAULT_IMAGES\s*=\s*\{(.*?)^\}", content,
                          re.DOTALL | re.MULTILINE)
        if not match:
            raise ValueError(f"_DEFAULT_IMAGES not found in {self.registry_path}")
        images = {}
        for constant, image in re.findall(r'^\s*([A-Z][A-Z0-9_]*):\s*"([^"]+)"',
                                          match.group(1), re.MULTILINE):
            if constant not in ids:
                raise ValueError(f"Unknown registry ID {constant} in {self.registry_path}")
            images[ids[constant]] = image
        return images

    def extract_images(self, images: Dict[str, str]) -> Tuple[Dict[str, ComponentVersion], list]:
        """Compare each registry image with its upstream release.

        Returns (components, unknown_keys) where unknown_keys lists registry IDs
        that are in neither COMPONENT_REPOS nor SKIPPED_IMAGES.
        """
        components: Dict[str, ComponentVersion] = {}
        unknown_keys = []
        for key, image in images.items():
            if key in SKIPPED_IMAGES:
                continue
            if key not in COMPONENT_REPOS:
                unknown_keys.append(key)
                continue
            repo, tag_prefix = COMPONENT_REPOS[key]
            components[key] = self._component(key, image, repo, tag_prefix, "l2")
        return components, unknown_keys

    def extract_l1_images(self) -> Dict[str, ComponentVersion]:
        participant = hard_forks.l1_test_participant(self.repo_root)["participant"]
        components = {}
        for field, (name, repo, tag_prefix) in L1_IMAGES.items():
            components[name] = self._component(name, participant[field], repo, tag_prefix, "l1")
        return components

    def extract_tools(self) -> Dict[str, ComponentVersion]:
        tools = tomllib.loads((self.repo_root / "mise.toml").read_text()).get("tools", {})
        components = {}
        for tool, (name, repo, tag_prefix) in MISE_TOOLS.items():
            if tool not in tools:
                print(f"Warning: {tool} not found in mise.toml.")
                continue
            components[name] = self._component(name, f"{tool}@{tools[tool]}", repo,
                                               tag_prefix, "tool", version=str(tools[tool]))
        action = yaml.safe_load((self.repo_root / SETUP_ACTION).read_text())
        for step in action["runs"]["steps"]:
            if step.get("uses", "").startswith("foundry-rs/foundry-toolchain@"):
                version = step["with"]["version"]
                components["foundry"] = self._component(
                    "foundry", f"foundry@{version}", "foundry-rs/foundry", "v", "tool",
                    version=version)
        return components

    def _component(self, key: str, image: str, repo: str, tag_prefix: str, group: str,
                   version: Optional[str] = None) -> ComponentVersion:
        print(f"  {key}")
        tag = version or self._tag_from_image(image)
        version = self._strip_tag_prefix(tag, "v")
        if (repo, tag_prefix) not in self._latest:
            self._latest[(repo, tag_prefix)] = self._get_latest_version(repo, tag_prefix)
        latest_version = self._latest[(repo, tag_prefix)]
        status = self._determine_status(version, latest_version)

        pin_reason = None
        # A pin only ever downgrades a "behind" result: once the component
        # catches up, its real status is reported again, which is the signal to
        # delete the entry.
        if status == STATUS_BEHIND and key in PINNED_VERSIONS:
            pin_reason = PINNED_VERSIONS[key]
            status = STATUS_PINNED
        elif status == STATUS_BEHIND and group != "tool":
            # A release often lands days before its image, or never gets one in
            # the registry we pull from: bumping to it would break the devnet.
            wanted = self._image_tag_for(tag, latest_version)
            if self._image_published(image, wanted) is False:
                pin_reason = f"No `{wanted}` image published yet."
                status = STATUS_PINNED

        return ComponentVersion(
            version=version,
            image=image,
            latest_version=latest_version,
            version_source_url=self._release_url(repo, version, tag_prefix),
            latest_version_source_url=self._release_url(repo, latest_version, tag_prefix),
            status=status,
            pin_reason=pin_reason,
            group=group,
        )

    @staticmethod
    def _tag_from_image(image: str) -> str:
        """The tag of a Docker image reference."""
        name = image.rsplit("/", 1)[-1]
        return name.rsplit(":", 1)[-1] if ":" in name else "latest"

    @classmethod
    def _image_tag_for(cls, our_tag: str, version: str) -> str:
        """The image tag `version` would have, given how our tag is spelled:
        same `v` prefix, same build-variant suffix (`-cdk`, `-alpine`)."""
        prefix = "v" if our_tag.startswith("v") else ""
        return f"{prefix}{version}{cls._variant_suffix(our_tag)}"

    @staticmethod
    def _image_published(image: str, tag: str) -> Optional[bool]:
        """Whether `tag` exists for the repository of `image`, read anonymously
        from its registry (Docker Registry v2 API). None if the registry could
        not be asked."""
        name = image.rsplit(":", 1)[0] if ":" in image.rsplit("/", 1)[-1] else image
        host, _, repository = name.partition("/")
        if "." not in host:
            # Docker Hub: `nethermind/nethermind`, or `library/<name>` for official images.
            repository = name if "/" in name else f"library/{name}"
            host = "registry-1.docker.io"
        headers = {"Accept": ", ".join([
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.oci.image.manifest.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
            "application/vnd.docker.distribution.manifest.v2+json",
        ])}
        try:
            token_url = {
                "registry-1.docker.io": "https://auth.docker.io/token?service=registry.docker.io",
                "ghcr.io": "https://ghcr.io/token?",
            }.get(host)
            if token_url:
                token = requests.get(f"{token_url}&scope=repository:{repository}:pull", timeout=30)
                token.raise_for_status()
                headers["Authorization"] = f"Bearer {token.json()['token']}"
            response = requests.head(f"https://{host}/v2/{repository}/manifests/{tag}",
                                     headers=headers, timeout=30)
        except (requests.RequestException, KeyError, ValueError) as e:
            print(f"Could not check {name}:{tag}: {e}")
            return None
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        print(f"Could not check {name}:{tag}: HTTP {response.status_code}")
        return None

    @classmethod
    def _release_url(cls, repo: str, version: Optional[str],
                     tag_prefix: str = "v") -> Optional[str]:
        """Build a browsable release URL for a component version."""
        if not version:
            return None
        if version in ("latest", "main", "master"):
            return f"https://github.com/{repo}/releases/latest"
        return f"https://github.com/{repo}/releases/tag/{tag_prefix}{cls._without_variant_suffix(version)}"

    @staticmethod
    def _is_prerelease(tag_name: str) -> bool:
        """Whether a tag looks like a prerelease rather than a stable version."""
        return PRERELEASE.search(tag_name) is not None

    @classmethod
    def _variant_suffix(cls, version: str) -> str:
        """A build-variant suffix (`-cdk`, `-alpine`): a dash followed by a
        letter. A dash followed by a digit is part of the version (op-erigon
        `2.61.3-0.9.5`), and a prerelease suffix is part of the version too."""
        if cls._is_prerelease(version):
            return ""
        match = re.search(r"-[A-Za-z][\w.-]*$", version)
        return match.group(0) if match else ""

    @classmethod
    def _without_variant_suffix(cls, version: str) -> str:
        suffix = cls._variant_suffix(version)
        return version[:-len(suffix)] if suffix else version

    def _get_latest_version(self, repo: str, tag_prefix: str = "v") -> Optional[str]:
        """Fetch the latest stable release version for a repo."""
        if tag_prefix not in ("", "v"):
            return self._get_latest_prefixed_version(repo, tag_prefix)

        release = self._github_get(f"repos/{repo}/releases/latest",
                                   allow_missing=True)
        if release and release.get("tag_name"):
            tag = release["tag_name"]
            if not self._is_prerelease(tag):
                return self._strip_tag_prefix(tag, tag_prefix)

        # Some repos publish prereleases as "latest", or never cut releases at
        # all; fall back to the newest stable tag.
        tags = self._github_get(f"repos/{repo}/tags?per_page=100")
        if isinstance(tags, list):
            for tag in tags:
                name = tag.get("name", "")
                if name and not self._is_prerelease(name):
                    return self._strip_tag_prefix(name, tag_prefix)

        print(f"No stable release or tag found for {repo}.")
        return None

    def _get_latest_prefixed_version(self, repo: str, tag_prefix: str) -> Optional[str]:
        """Highest stable `<prefix><version>` tag of a monorepo."""
        # This endpoint returns every matching ref at once and ignores paging.
        refs = self._github_get(f"repos/{repo}/git/matching-refs/tags/{tag_prefix}")
        versions = []
        for ref in refs if isinstance(refs, list) else []:
            version = ref["ref"].removeprefix(f"refs/tags/{tag_prefix}")
            if not self._is_prerelease(version) and self._version_key(version):
                versions.append(version)
        if not versions:
            print(f"No stable {tag_prefix} tag found for {repo}.")
            return None
        return max(versions, key=self._version_key)

    @staticmethod
    def _strip_tag_prefix(tag: str, tag_prefix: str) -> str:
        """Drop the release tag prefix: `v1.8.5`/`op-node/v1.8.5` -> `1.8.5`."""
        if tag_prefix and tag.startswith(tag_prefix):
            return tag[len(tag_prefix):]
        return tag.lstrip("v")

    def _determine_status(self, version: Optional[str],
                          latest_version: Optional[str]) -> Optional[str]:
        """Compare a deployed version against the latest stable release."""
        if not version or not latest_version:
            return None

        ours = self._version_key(version)
        theirs = self._version_key(latest_version)
        if ours is None or theirs is None:
            return None

        if ours > theirs:
            return STATUS_NEWER
        if ours < theirs:
            return STATUS_BEHIND

        # Same version numbers: a prerelease of the release rather than the
        # release itself. A build-variant suffix (`-cdk`) is not a version
        # difference and is ignored.
        if self._is_prerelease(version) and not self._is_prerelease(latest_version):
            return STATUS_NEWER
        return STATUS_MATCHES

    @classmethod
    def _version_key(cls, version: str) -> Optional[tuple]:
        """Turn a version string into a comparable tuple of its numbers, ignoring
        prerelease and build-variant suffixes. Every number counts, so the
        op-erigon `2.61.3-0.9.5` sorts before `2.61.3-0.10.1`."""
        core = cls._without_variant_suffix(version.lstrip("v"))
        prerelease = PRERELEASE.search(core)
        if prerelease:
            core = core[:prerelease.start()]
        if not re.fullmatch(r"\d+(?:[.-]\d+)*", core):
            return None
        numbers = [int(part) for part in re.split(r"[.-]", core)]
        # Pad so that "2.9" and "2.9.0" compare equal.
        while len(numbers) < 6:
            numbers.append(0)
        return tuple(numbers)

    # --- packages ----------------------------------------------------------

    def extract_packages(self) -> Dict[str, PackageVersion]:
        """Extract external Kurtosis package pins from the kurtosis.yml replace block."""
        packages: Dict[str, PackageVersion] = {}

        try:
            kurtosis_yaml = yaml.safe_load(self.kurtosis_yaml_path.read_text())
        except Exception as e:
            print(f"Error reading {self.kurtosis_yaml_path}: {e}")
            return packages

        replace_options = (kurtosis_yaml or {}).get("replace") or {}
        if not replace_options:
            print("No `replace` block found in kurtosis.yml, skipping packages.")
            return packages

        for package_locator, replacement in replace_options.items():
            # A replacement may redirect to a different repo (e.g. a fork) and
            # optionally append `@<tag|branch|commit>`. The pin is what actually
            # gets resolved, so report against the replacement target.
            target, _, pin = replacement.partition("@")
            repo = self._repo_from_locator(target)
            if not repo:
                print(f"Could not derive a GitHub repo from '{target}', skipping.")
                continue

            pin = pin or "HEAD"
            pin_date = self._get_ref_date(repo, pin)
            # A commit pin means upstream ships faster than it tags: follow its HEAD.
            tracking_mode = ("head" if pin == "HEAD" or self._is_commit_sha(pin)
                             else "release")

            if tracking_mode == "head":
                latest_version, latest_version_date = self._get_head_version(repo)
                status, commit_distance = self._determine_head_tracked_status(
                    repo, pin, latest_version)
            else:
                latest_version, latest_version_date = self._get_latest_package_version(repo)
                status, commit_distance = self._determine_package_status(
                    repo, pin, pin_date, latest_version, latest_version_date)

            pin_reason = None
            if status == STATUS_BEHIND and package_locator in PINNED_PACKAGES:
                pin_reason = PINNED_PACKAGES[package_locator]
                status = STATUS_PINNED

            packages[package_locator] = PackageVersion(
                pin=pin,
                pin_date=pin_date,
                pin_source_url=self._package_source_url(repo, pin),
                latest_version=latest_version,
                latest_version_date=latest_version_date,
                latest_version_source_url=(
                    self._package_source_url(repo, latest_version)
                    if latest_version else None
                ),
                status=status,
                commit_distance=commit_distance,
                tracking_mode=tracking_mode,
                pin_reason=pin_reason,
                core=package_locator in CORE_PACKAGES,
            )

        return packages

    @staticmethod
    def _repo_from_locator(locator: str) -> Optional[str]:
        """Turn a github.com/org/repo[/sub/path] locator into 'org/repo'."""
        match = re.match(r"(?:https?://)?github\.com/([^/]+)/([^/@]+)", locator)
        return f"{match.group(1)}/{match.group(2)}" if match else None

    @staticmethod
    def _is_commit_sha(ref: str) -> bool:
        return bool(re.fullmatch(r"[0-9a-f]{7,40}", ref or "", re.IGNORECASE))

    def _get_ref_date(self, repo: str, ref: str) -> Optional[str]:
        """Resolve the commit date (YYYY-MM-DD) of a tag, branch or commit."""
        if not ref:
            return None

        candidates = [ref]
        # Kurtosis pins are often written `@v1.1.0` while the upstream tag is
        # `1.1.0` (or the reverse), so try both spellings before giving up.
        if not self._is_commit_sha(ref):
            stripped = ref.lstrip("v")
            candidates += [stripped, f"v{stripped}"]

        for candidate in dict.fromkeys(candidates):
            data = self._github_get(f"repos/{repo}/commits/{candidate}",
                                    allow_missing=True)
            if data:
                date = data.get("commit", {}).get("committer", {}).get("date")
                return date[:10] if date else None
        return None

    def _get_latest_package_version(self, repo: str) -> tuple:
        """Return (version, date) of the newest release, falling back to tags."""
        # A 404 here just means the repo has never published a release.
        release = self._github_get(f"repos/{repo}/releases/latest",
                                   allow_missing=True)
        if release and release.get("tag_name"):
            return release["tag_name"], (release.get("published_at") or "")[:10] or None

        tags = self._github_get(f"repos/{repo}/tags?per_page=1")
        if isinstance(tags, list) and tags:
            tag_name = tags[0].get("name")
            if tag_name:
                return tag_name, self._get_ref_date(repo, tag_name)

        print(f"No releases or tags found for {repo}.")
        return None, None

    def _get_head_version(self, repo: str) -> tuple:
        """Return (sha, date) of the default branch HEAD."""
        commits = self._github_get(f"repos/{repo}/commits?per_page=1")
        if isinstance(commits, list) and commits:
            sha = commits[0].get("sha", "")
            date = commits[0].get("commit", {}).get("committer", {}).get("date")
            return sha or None, date[:10] if date else None
        return None, None

    def _determine_head_tracked_status(self, repo: str, pin: str,
                                       head_version: Optional[str]) -> tuple:
        """Judge a pin that tracks HEAD rather than releases: any pin short of
        the branch tip is behind, so the weekly bump follows HEAD."""
        if not head_version:
            return None, None

        if pin[:12] == head_version[:12]:
            return STATUS_MATCHES, None

        comparison = self._github_get(f"repos/{repo}/compare/{head_version}...{pin}")
        if comparison:
            behind_by = comparison.get("behind_by", 0)
            if behind_by > 0:
                return STATUS_BEHIND, f"{behind_by} commits behind HEAD"
            if comparison.get("ahead_by", 0) > 0:
                # Pinned to an unmerged or since-rewritten commit.
                return STATUS_NEWER, (
                    f"{comparison['ahead_by']} commits ahead of HEAD")

        # Compare API unavailable: the pin differs from HEAD, and bumping to HEAD is safe.
        return STATUS_BEHIND, None

    def _package_source_url(self, repo: str, ref: str) -> Optional[str]:
        """Build a browsable URL for a package ref."""
        if not ref:
            return None
        if self._is_commit_sha(ref):
            return f"https://github.com/{repo}/tree/{ref}"
        return f"https://github.com/{repo}/releases/tag/{ref}"

    def _determine_package_status(self, repo: str, pin: str,
                                  pin_date: Optional[str],
                                  latest_version: Optional[str],
                                  latest_version_date: Optional[str]) -> tuple:
        """Determine whether a package pin is up to date, and how far it drifted.

        Returns (status, commit_distance) where commit_distance is a short
        human-readable summary like "14 commits behind 1.0.0", or None.
        """
        if not latest_version:
            return None, None

        # A tag pin can be compared directly against the latest release tag.
        if not self._is_commit_sha(pin) and not self._is_commit_sha(latest_version):
            if pin.lstrip("v") == latest_version.lstrip("v"):
                return STATUS_MATCHES, None
            return self._determine_status(
                pin.lstrip("v"), latest_version.lstrip("v")), None

        # A commit pin equal to the latest ref is up to date.
        if pin[:12] == (latest_version or "")[:12]:
            return STATUS_MATCHES, None

        # For a commit pin, ask GitHub where it sits relative to the latest
        # release. Comparing raw dates would be wrong: a commit can be authored
        # after a release was published while still being an ancestor of it.
        comparison = self._github_get(f"repos/{repo}/compare/{latest_version}...{pin}")
        if comparison:
            behind_by = comparison.get("behind_by", 0)
            ahead_by = comparison.get("ahead_by", 0)
            if behind_by > 0:
                return STATUS_BEHIND, f"{behind_by} commits behind {latest_version}"
            if ahead_by > 0:
                return STATUS_NEWER, f"{ahead_by} commits ahead of {latest_version}"
            return STATUS_MATCHES, None

        # Fall back to dates only when the comparison is unavailable.
        if pin_date and latest_version_date:
            if pin_date > latest_version_date:
                return STATUS_NEWER, None
            if pin_date < latest_version_date:
                return STATUS_BEHIND, None
            return STATUS_MATCHES, None

        return None, None

    # --- github ------------------------------------------------------------

    @staticmethod
    def _github_get(path: str, allow_missing: bool = False):
        """GET a GitHub API path, returning parsed JSON or None.

        Set allow_missing for endpoints where a 404 is a legitimate answer
        rather than a failure — a repo that has never cut a release returns 404
        from /releases/latest, and logging that as an error is just noise.
        """
        try:
            response = requests.get(
                f"https://api.github.com/{path}", timeout=10,
                headers={"Authorization": f'token {os.getenv("GITHUB_TOKEN")}'})
            if response.status_code == 200:
                return response.json()
            if response.status_code == 404 and allow_missing:
                return None
            print(f"Error fetching {path}: {response.status_code}")
        except Exception as e:
            print(f"Error fetching {path}: {e}")
        return None

    # --- matrix ------------------------------------------------------------

    def generate_version_matrix(self) -> Tuple[Dict, list]:
        """Build the full version matrix."""
        registry = self.registry_images()

        print("Extracting images...")
        images, unknown_keys = self.extract_images(registry)
        images.update(self.extract_l1_images())

        print("Extracting CI tools...")
        tools = self.extract_tools()

        print("Extracting external Kurtosis packages...")
        packages = self.extract_packages()

        print("Extracting hard forks...")
        forks = hard_forks.extract(self.repo_root, registry["op-node"], registry["op-deployer"])

        matrix = {
            "images": {name: asdict(component) for name, component in images.items()},
            "skipped_images": {key: {"image": registry[key]}
                               for key in SKIPPED_IMAGES if key in registry},
            "tools": {name: asdict(component) for name, component in tools.items()},
            "packages": {name: asdict(package) for name, package in packages.items()},
            "hard_forks": forks,
            "summary": {
                "total_images": len(images),
                "total_tools": len(tools),
                "total_packages": len(packages),
                "skipped_images": len(SKIPPED_IMAGES),
            },
        }
        return matrix, unknown_keys

    def save_matrix_json(self, matrix: Dict, output_path: Optional[Path] = None):
        """Save the matrix as a JSON file, with sorted keys so reruns diff cleanly."""
        if output_path is None:
            output_path = self.repo_root / "scripts" / "version-matrix" / "matrix.json"
        output_path.write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n")
        print(f"Version matrix saved to {output_path}")


def main():
    if not os.getenv("GITHUB_TOKEN"):
        print("Error: GITHUB_TOKEN environment variable is not set.")
        print("Please set it to access GitHub API for version information.")
        exit(1)

    repo_root = Path(__file__).parent.parent.parent
    extractor = VersionMatrixExtractor(repo_root)

    print("Starting version matrix extraction...")
    matrix, unknown_keys = extractor.generate_version_matrix()
    extractor.save_matrix_json(matrix)

    summary = matrix["summary"]
    print("\n=== Version Matrix Summary ===")
    print(f"Images tracked: {summary['total_images']}")
    print(f"Images skipped: {summary['skipped_images']}")
    print(f"CI tools tracked: {summary['total_tools']}")
    print(f"Packages tracked: {summary['total_packages']}")

    # An image in neither COMPONENT_REPOS nor SKIPPED_IMAGES is a gap: it was
    # added to registry.star without deciding how to track it.
    if unknown_keys:
        print("\nUntracked images found in registry.star. Add them to "
              "COMPONENT_REPOS or SKIPPED_IMAGES in this script:")
        for key in unknown_keys:
            print(f"  - {key}")
        exit(1)


if __name__ == "__main__":
    main()
