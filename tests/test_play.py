from __future__ import annotations

import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLAY_ROOT = ROOT / "play"
SPEC = importlib.util.spec_from_file_location("build_play", ROOT / "build_play.py")
assert SPEC and SPEC.loader
build_play = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_play)


def run_script(script: str, *args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> dict:
    completed = subprocess.run(
        [sys.executable, "-c", script, *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    if completed.returncode:
        raise AssertionError(f"step failed ({completed.returncode}): {completed.stderr}")
    return json.loads(completed.stdout)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def audit(
    repo: Path,
    maximum: int = 3,
    verification: str = "static",
    demo: str = "",
    env: dict[str, str] | None = None,
    assessment_cwd: Path | None = None,
) -> dict:
    validated = run_script(
        build_play.VALIDATE_SCRIPT,
        str(repo),
        "README.md,docs",
        str(maximum),
        "",
        verification,
        demo,
        env=env,
    )
    docs = run_script(build_play.SCAN_DOCS_SCRIPT, validated["repo"], validated["docs_spec"], demo, env=env)
    state = run_script(build_play.SCAN_REPO_SCRIPT, validated["repo"], "", demo, env=env)
    return run_script(
        build_play.ASSESS_SCRIPT,
        validated["repo"],
        docs["payload"],
        state["payload"],
        str(maximum),
        verification,
        demo,
        cwd=assessment_cwd,
        env=env,
    )


class DocumentationContractRefereeTest(unittest.TestCase):
    def test_coherent_repository_returns_contract_holds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            write(repo / "package.json", json.dumps({"version": "1.2.0", "scripts": {"build": "tsc", "test": "node --test"}}))
            write(repo / "package-lock.json", "{}")
            write(repo / ".env.example", "API_URL=https://example.test\n")
            write(repo / "docs" / "setup.md", "# Setup\n")
            write(repo / "README.md", "# App\n\nCurrent version: 1.2.0\n\n[Setup](docs/setup.md)\n\n```sh\nnpm ci\nnpm run build\nAPI_URL=https://example.test npm test\n```\n")

            result = audit(repo)

            self.assertEqual("contract_holds", result["verdict"])
            self.assertEqual([], result["findings"])
            self.assertTrue(result["read_only"])

    def test_stale_repository_returns_three_prioritized_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            write(repo / "package.json", json.dumps({"version": "1.0.0", "scripts": {"test": "node --test"}}))
            write(repo / "package-lock.json", "{}")
            write(repo / "README.md", "# App\n\nCurrent version: 2.0.0\n\n[Setup](docs/missing.md)\n\n```sh\npnpm install\nnpm run build\n```\n")
            (repo / "docs").mkdir()

            result = audit(repo)

            self.assertEqual("contract_broken", result["verdict"])
            self.assertGreaterEqual(result["finding_count"], 4)
            self.assertEqual(3, len(result["findings"]))
            self.assertEqual(result["finding_count"] - 3, result["omitted_count"])
            self.assertEqual(
                {"broken_local_link", "missing_package_script", "package_manager_mismatch"},
                {item["rule"] for item in result["findings"]},
            )

    def test_fixing_contract_mismatches_restores_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            write(repo / "package.json", json.dumps({"version": "2.0.0", "scripts": {"build": "tsc"}}))
            write(repo / "package-lock.json", "{}")
            write(repo / "docs" / "setup.md", "# Setup\n")
            write(repo / "README.md", "# App\n\nCurrent version: 2.0.0\n\n[Setup](docs/setup.md)\n\n```sh\nnpm ci\nnpm run build\n```\n")

            result = audit(repo)

            self.assertEqual("contract_holds", result["verdict"])

    def test_documented_make_and_just_commands_are_refereed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            write(repo / "README.md", "# App\n\n```sh\nmake release\njust verify\n```\n")
            write(repo / "Makefile", "build:\n\t@echo build\n")
            write(repo / "justfile", "test:\n    echo test\n")

            result = audit(repo, maximum=5)

            self.assertEqual("contract_broken", result["verdict"])
            self.assertTrue(
                {"missing_make_target", "missing_just_recipe"}
                <= {item["rule"] for item in result["findings"]},
            )
            self.assertEqual(2, result["checked"]["documented_commands"])

    def test_generated_play_is_current_and_has_no_early_frontmatter_close(self) -> None:
        expected = build_play.build()
        actual = (PLAY_ROOT / "main.ts").read_text(encoding="utf-8")
        self.assertEqual(expected, actual)
        self.assertEqual(1, actual.count("*/"))
        self.assertEqual(4, actual.count("type: process.exec"))
        self.assertEqual(4, actual.count("@resource{"))
        self.assertIn(" *   version: 0.2.0", actual)
        self.assertIn(" * - name: verification", actual)
        self.assertIn(" * - name: demo", actual)
        expected_resources = {
            "validate.py": build_play.VALIDATE_SCRIPT,
            "scan_docs.py": build_play.SCAN_DOCS_SCRIPT,
            "scan_repo.py": build_play.SCAN_REPO_SCRIPT,
            "assess.py": build_play.ASSESS_SCRIPT,
        }
        for name, expected_script in expected_resources.items():
            self.assertEqual(
                expected_script,
                (PLAY_ROOT / "resources" / name).read_text(encoding="utf-8"),
            )

    def test_presentation_meets_documented_rote_static_lint_contract(self) -> None:
        actual = (PLAY_ROOT / "main.ts").read_text(encoding="utf-8")
        self.assertEqual(1, actual.count("new FlowOutput()"))
        self.assertGreaterEqual(actual.count("out.human("), 1)
        self.assertGreaterEqual(actual.count("out.summary("), 1)
        self.assertGreaterEqual(actual.count("out.result({"), 1)
        self.assertNotIn("console.log(", actual)
        self.assertNotIn("out.emit(", actual)

    def test_payloads_are_scalar_base64_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            write(repo / "README.md", "# Empty\n")
            docs = run_script(build_play.SCAN_DOCS_SCRIPT, str(repo), "README.md", "")
            decoded = json.loads(base64.b64decode(docs["payload"]).decode())
            self.assertEqual(["README.md"], decoded["docs"])

    def test_validation_rejects_documentation_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            write(repo / "README.md", "# Safe\n")
            completed = subprocess.run(
                [sys.executable, "-c", build_play.VALIDATE_SCRIPT, str(repo), "../outside.md", "3", "", "static", ""],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("escapes repository", completed.stderr)

    def test_empty_documentation_requires_review_instead_of_false_hold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            write(repo / "README.md", "# Notes\n\nGeneral prose without executable claims.\n")

            result = audit(repo)

            self.assertEqual("review_required", result["verdict"])
            self.assertEqual("no_checkable_claims", result["findings"][0]["rule"])
            self.assertEqual(0, result["checked"]["total_claims"])

    def test_markdown_heading_anchor_is_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            write(repo / "README.md", "# App\n\n[Install](docs/setup.md#install-now)\n")
            write(repo / "docs" / "setup.md", "# Install now\n")

            coherent = audit(repo)
            self.assertEqual("contract_holds", coherent["verdict"])
            self.assertEqual(1, coherent["checked"]["anchors"])

            write(repo / "README.md", "# App\n\n[Install](docs/setup.md#missing-heading)\n")
            stale = audit(repo)
            self.assertEqual("contract_broken", stale["verdict"])
            self.assertEqual("broken_local_anchor", stale["findings"][0]["rule"])

    def test_missing_executable_is_reported_as_prerequisite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            write(repo / "README.md", "# App\n\n```sh\ndefinitely-not-installed-dcr verify\n```\n")

            result = audit(repo)

            self.assertEqual("review_required", result["verdict"])
            self.assertIn("missing_prerequisite", {item["rule"] for item in result["findings"]})
            self.assertEqual(1, result["checked"]["prerequisites"])

    def test_non_shell_code_fences_are_not_treated_as_prerequisites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            write(
                repo / "README.md",
                '# App\n\n```json\n{"scripts": {"build": "tsc"}}\n```\n\n```python\nprint("hello")\n```\n',
            )

            result = audit(repo)

            self.assertEqual("review_required", result["verdict"])
            self.assertEqual(0, result["checked"]["prerequisites"])
            self.assertEqual({"no_checkable_claims"}, {item["rule"] for item in result["findings"]})

    def test_safe_help_never_executes_the_documented_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            marker = repo / "documented-command-ran.txt"
            script = f'"{sys.executable}" -c "from pathlib import Path; Path(r\'{marker}\').write_text(r\'ran\')"'
            write(repo / "package.json", json.dumps({"scripts": {"build": script}}))
            write(repo / "package-lock.json", "{}")
            write(repo / "README.md", "# App\n\n```sh\nnpm run build --definitely-missing-dcr-flag\n```\n")

            result = audit(repo, maximum=10, verification="safe-help", env=os.environ.copy())

            self.assertFalse(marker.exists())
            self.assertEqual(0, result["documented_commands_executed"])
            self.assertEqual(1, result["checked"]["safe_help_checks"])
            self.assertIn("flag_not_in_safe_help", {item["rule"] for item in result["findings"]})

    def test_safe_help_rejects_repository_local_path_shadowing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            marker = repo / "shadowed-command-ran.txt"
            if os.name == "nt":
                write(repo / "npm.cmd", f'@echo off\r\necho reached>"{marker}"\r\nexit /b 0\r\n')
            else:
                fake = repo / "npm"
                write(fake, f"#!/bin/sh\nprintf reached > '{marker}'\n")
                fake.chmod(0o755)
            write(repo / "README.md", "# App\n\n```sh\nnpm --version\n```\n")
            env = os.environ.copy()
            env["PATH"] = str(repo) + os.pathsep + env.get("PATH", "")

            result = audit(repo, maximum=10, verification="safe-help", env=env, assessment_cwd=repo)

            self.assertFalse(marker.exists())
            self.assertEqual(1, result["checked"]["safe_help_attempts"])
            self.assertEqual(1, result["checked"]["safe_help_checks"])

    def test_safe_help_caps_total_probe_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            runner_bin = root / "runner-bin"
            repo.mkdir()
            runner_bin.mkdir()
            if os.name == "nt":
                write(runner_bin / "npm.cmd", "@echo off\r\necho --flag-0 --flag-1 --flag-2 --flag-3 --flag-4 --flag-5 --flag-6\r\nexit /b 0\r\n")
            else:
                fake = runner_bin / "npm"
                write(fake, "#!/bin/sh\nprintf '%s\\n' '--flag-0 --flag-1 --flag-2 --flag-3 --flag-4 --flag-5 --flag-6'\n")
                fake.chmod(0o755)
            commands = "\n".join(f"npm --flag-{index}" for index in range(7))
            write(repo / "README.md", f"# App\n\n```sh\n{commands}\n```\n")
            env = os.environ.copy()
            env["PATH"] = str(runner_bin)

            result = audit(repo, maximum=10, verification="safe-help", env=env)

            self.assertEqual(5, result["checked"]["safe_help_attempts"])
            self.assertEqual(5, result["checked"]["safe_help_checks"])
            self.assertIn("safe_help_limit_reached", {item["rule"] for item in result["findings"]})

    def test_built_in_demos_are_deterministic_and_opposite(self) -> None:
        coherent = audit(ROOT, demo="coherent")
        stale = audit(ROOT, demo="stale")

        self.assertEqual("contract_holds", coherent["verdict"])
        self.assertEqual("contract_broken", stale["verdict"])
        self.assertEqual("coherent", coherent["demo"])
        self.assertEqual("stale", stale["demo"])
        self.assertEqual(4, stale["finding_count"])

    def test_checked_in_demo_repositories_have_opposite_verdicts(self) -> None:
        coherent = audit(ROOT / "examples" / "coherent")
        stale = audit(ROOT / "examples" / "stale")
        self.assertEqual("contract_holds", coherent["verdict"])
        self.assertEqual("contract_broken", stale["verdict"])
        self.assertEqual(
            {"broken_local_link", "missing_package_script", "package_manager_mismatch"},
            {item["rule"] for item in stale["findings"]},
        )


if __name__ == "__main__":
    unittest.main()
