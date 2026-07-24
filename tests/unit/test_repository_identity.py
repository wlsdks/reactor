from __future__ import annotations

import subprocess
from pathlib import Path
from shutil import which

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPOSITORY_ROOT / "scripts" / "dev" / "verify-repository-identity.sh"
EXPECTED_ORIGIN = "https://github.com/wlsdks/reactor.git"
GIT = which("git")


def test_repository_identity_accepts_the_personal_reactor_remote() -> None:
    result = subprocess.run(  # noqa: S603 - repository-owned executable
        [VERIFY_SCRIPT],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "wlsdks/reactor" in result.stdout


def test_repository_identity_rejects_an_unapproved_remote(tmp_path: Path) -> None:
    assert GIT is not None
    subprocess.run([GIT, "init", "-q", tmp_path], check=True)  # noqa: S603
    subprocess.run(  # noqa: S603
        [GIT, "-C", tmp_path, "remote", "add", "origin", "https://example.test/reactor.git"],
        check=True,
    )

    result = subprocess.run(  # noqa: S603 - repository-owned executable
        [VERIFY_SCRIPT],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "repository identity mismatch" in result.stderr.lower()


@pytest.mark.parametrize(
    "instruction_path",
    [
        REPOSITORY_ROOT / "AGENTS.md",
        REPOSITORY_ROOT / "CLAUDE.md",
        REPOSITORY_ROOT / "apps" / "admin" / "AGENTS.md",
    ],
)
def test_agent_instructions_require_repository_identity_check(
    instruction_path: Path,
) -> None:
    instructions = instruction_path.read_text(encoding="utf-8")

    assert "verify-repository-identity.sh" in instructions
    assert "wlsdks/reactor" in instructions


def test_root_agent_instructions_pin_the_approved_origin() -> None:
    instructions = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert EXPECTED_ORIGIN in instructions


def test_tracked_source_omits_legacy_project_branding() -> None:
    assert GIT is not None
    legacy_prefix = bytes.fromhex("617263").decode()
    case_insensitive_patterns = (
        r"(^|[^[:alnum:]_])" + "as" + r"lan([^[:alnum:]_]|$)",
        rf"(^|[^[:alnum:]_]){legacy_prefix}[-_][[:alnum:]_-]+",
        rf"(^|[^[:alnum:]_]){legacy_prefix}[[:space:]]+reactor([^[:alnum:]_]|$)",
    )
    case_sensitive_patterns = (
        rf"({legacy_prefix.capitalize()}|{legacy_prefix})[A-Z][[:alnum:]_]*",
        rf"{legacy_prefix.upper()}_[A-Z0-9_]+",
    )
    insensitive_result = subprocess.run(  # noqa: S603
        [
            GIT,
            "-C",
            REPOSITORY_ROOT,
            "grep",
            "-I",
            "-i",
            "-n",
            "-E",
            *(argument for pattern in case_insensitive_patterns for argument in ("-e", pattern)),
            "--",
            ".",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    sensitive_result = subprocess.run(  # noqa: S603
        [
            GIT,
            "-C",
            REPOSITORY_ROOT,
            "grep",
            "-I",
            "-n",
            "-E",
            *(argument for pattern in case_sensitive_patterns for argument in ("-e", pattern)),
            "--",
            ".",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert insensitive_result.returncode == 1, insensitive_result.stdout
    assert sensitive_result.returncode == 1, sensitive_result.stdout


def test_reachable_commits_use_github_noreply_identity() -> None:
    assert GIT is not None
    result = subprocess.run(  # noqa: S603
        [GIT, "-C", REPOSITORY_ROOT, "log", "--format=%ae"],
        check=True,
        capture_output=True,
        text=True,
    )
    emails = {line.strip() for line in result.stdout.splitlines() if line.strip()}

    assert emails
    assert all(email.endswith("@users.noreply.github.com") for email in emails)
