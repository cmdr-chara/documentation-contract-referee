import base64, json, os, pathlib, re, subprocess, sys, tempfile

repo = pathlib.Path(sys.argv[1]).resolve()
docs = json.loads(base64.b64decode(sys.argv[2]).decode())
state = json.loads(base64.b64decode(sys.argv[3]).decode())
maximum = int(sys.argv[4])
verification = sys.argv[5]
demo = sys.argv[6]
findings = []
seen = set()
safe_help_checks = 0
safe_help_attempts = 0

def add(rule, severity, confidence, title, evidence, fix):
    key = (rule, title, evidence)
    if key not in seen:
        seen.add(key)
        findings.append({
            "rule": rule, "severity": severity, "confidence": confidence,
            "title": title, "evidence": evidence, "suggested_fix": fix,
        })

def heading_anchors(path):
    anchors = set()
    occurrences = {}
    text = path.read_text(encoding="utf-8", errors="replace")[:1_000_000]
    for match in re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*#*\s*$", text):
        heading = re.sub(r"`([^`]*)`", r"\1", match.group(1))
        heading = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading)
        heading = re.sub(r"<[^>]+>", "", heading).lower().strip()
        slug = re.sub(r"[^\w\- ]", "", heading, flags=re.UNICODE)
        slug = re.sub(r"\s+", "-", slug)
        index = occurrences.get(slug, 0)
        occurrences[slug] = index + 1
        anchors.add(slug if index == 0 else f"{slug}-{index}")
    return anchors

for ref in docs["link_refs"]:
    doc = repo / ref["doc"]
    target = (doc.parent / ref["target"]).resolve() if ref["target"] else doc.resolve()
    if demo:
        target_exists = bool(ref.get("demo_exists"))
        anchors = set(ref.get("demo_anchors", []))
    else:
        try:
            target.relative_to(repo)
        except ValueError:
            add("link_outside_repo", "warning", "high", "Documentation link escapes the repository", f'{ref["doc"]} -> {ref["target"]}', "Use a repository-relative target inside the project or an explicit trusted URL.")
            continue
        target_exists = target.exists()
        anchors = heading_anchors(target) if target_exists and target.is_file() and target.suffix.lower() in {".md", ".mdx"} else set()
    if not target_exists:
        add("broken_local_link", "error", "high", "Documented local link does not exist", f'{ref["doc"]} -> {ref["target"]}', "Restore the target or update the link to the current path.")
    elif ref.get("fragment") and ref["fragment"] not in anchors:
        add("broken_local_anchor", "error", "high", f'Documented heading `#{ref["fragment"]}` does not exist', f'{ref["doc"]} -> {ref["target"]}#{ref["fragment"]}', "Update the anchor or restore the matching Markdown heading.")

available_scripts = set(state["scripts"])
for ref in docs["script_refs"]:
    if ref["script"] not in available_scripts:
        add("missing_package_script", "error", "high", f'Documented script `{ref["script"]}` is unavailable', f'{ref["doc"]}: {ref["manager"]} run {ref["script"]}', "Update the command or add the intended script to package.json.")

available_make_targets = set(state["make_targets"])
for ref in docs["make_refs"]:
    if ref["target"] not in available_make_targets:
        add("missing_make_target", "error", "high", f'Documented Make target `{ref["target"]}` is unavailable', f'{ref["doc"]}: make {ref["target"]}', "Update the command or add the intended target to Makefile.")

available_just_recipes = set(state["just_recipes"])
for ref in docs["just_refs"]:
    if ref["recipe"] not in available_just_recipes:
        add("missing_just_recipe", "error", "high", f'Documented Just recipe `{ref["recipe"]}` is unavailable', f'{ref["doc"]}: just {ref["recipe"]}', "Update the command or add the intended recipe to justfile.")

active_locks = {name for name, present in state["locks"].items() if present}
documented_managers = {item["manager"] for item in docs["managers"]}
if len(active_locks) == 1:
    actual = next(iter(active_locks))
    for manager in sorted(documented_managers - {actual}):
        add("package_manager_mismatch", "warning", "medium", f'Docs use `{manager}` but the lockfile indicates `{actual}`', f'documented={manager}; lockfile={actual}', f"Replace setup commands with {actual}, or commit the matching lockfile intentionally.")

repo_versions = {item["version"] for item in state["versions"]}
for item in docs["versions"]:
    if len(repo_versions) == 1 and item["version"] not in repo_versions:
        actual = next(iter(repo_versions))
        add("version_mismatch", "warning", "medium", "Documented version differs from the root manifest", f'{item["doc"]}: {item["version"]}; manifest: {actual}', f"Update the documented version to {actual}, or remove a version that should not be maintained manually.")

declared_env = set(state["env_names"])
if declared_env:
    for item in docs["env_refs"]:
        if item["name"] not in declared_env:
            add("env_contract_gap", "watch", "medium", f'Environment variable `{item["name"]}` is absent from the env template', item["doc"], "Add it to the example env contract or clarify that it is optional/external.")

changed = set(state["changed"])
contract_files = {"package.json", "pyproject.toml", "Cargo.toml", "go.mod", "Makefile", "justfile"}
contract_changed = sorted(changed & contract_files)
docs_changed = sorted(path for path in changed if path.lower().endswith((".md", ".mdx")))
if contract_changed and not docs_changed:
    add("contract_changed_without_docs", "watch", "medium", "Executable contract changed without documentation changes", ", ".join(contract_changed), "Review the affected setup and runbook commands before release.")

primary_claim_count = (
    len(docs["script_refs"]) + len(docs["make_refs"]) + len(docs["just_refs"])
    + len(docs["link_refs"]) + len(docs["versions"]) + len(docs["env_refs"])
    + len({item["manager"] for item in docs["managers"]})
    + len(docs.get("prerequisite_refs", []))
)
if primary_claim_count == 0:
    add("no_checkable_claims", "watch", "high", "No checkable documentation claims were found", f'{len(docs["docs"])} document(s) scanned; 0 supported claims', "Add an executable command, local link, version, or environment contract, or widen docs_paths.")

prerequisite_refs = []
prerequisite_seen = set()
for ref in docs.get("prerequisite_refs", []):
    key = (ref["doc"], ref["command"], ref["executable"])
    if key not in prerequisite_seen:
        prerequisite_seen.add(key)
        prerequisite_refs.append(ref)

safe_help_allowlist = {
    "bun", "cargo", "docker", "gh", "git", "go", "kubectl", "make", "node", "npm",
    "pip", "pip3", "pnpm", "poetry", "pytest", "python", "python3", "ruff", "terraform",
    "tsc", "uv", "vite", "yarn",
}
safe_subcommands = {
    "git": {"branch", "checkout", "clone", "diff", "fetch", "log", "merge", "pull", "push", "remote", "restore", "show", "status", "switch", "tag"},
    "npm": {"ci", "exec", "help", "install", "run", "view"},
    "pnpm": {"add", "exec", "help", "install", "remove", "run"},
    "docker": {"build", "compose", "container", "image", "network", "run", "volume"},
    "gh": {"api", "auth", "issue", "pr", "release", "repo", "run", "workflow"},
    "kubectl": {"apply", "config", "describe", "diff", "get", "logs", "rollout"},
    "terraform": {"fmt", "init", "plan", "providers", "show", "validate", "version", "workspace"},
    "cargo": {"build", "check", "clippy", "fmt", "run", "test"},
    "go": {"build", "env", "fmt", "get", "list", "mod", "run", "test", "version"},
    "uv": {"add", "lock", "pip", "run", "sync", "tool", "venv"},
}

def path_is_inside(candidate, root):
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False

def trusted_which(executable):
    names = [executable]
    if os.name == "nt" and not pathlib.Path(executable).suffix:
        extensions = [item for item in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(os.pathsep) if item]
        names = [executable + extension.lower() for extension in extensions]
    seen_directories = set()
    for raw_directory in os.environ.get("PATH", "").split(os.pathsep):
        if not raw_directory:
            continue
        directory = pathlib.Path(raw_directory).expanduser()
        if not directory.is_absolute():
            continue
        try:
            directory = directory.resolve()
        except OSError:
            continue
        key = str(directory).casefold() if os.name == "nt" else str(directory)
        if key in seen_directories or path_is_inside(directory, repo):
            continue
        seen_directories.add(key)
        for name in names:
            candidate = (directory / name).resolve()
            if path_is_inside(candidate, repo):
                continue
            if candidate.is_file() and (os.name == "nt" or os.access(candidate, os.X_OK)):
                return str(candidate)
    return None

trusted_path_entries = []
for raw_directory in os.environ.get("PATH", "").split(os.pathsep):
    if not raw_directory:
        continue
    directory = pathlib.Path(raw_directory).expanduser()
    if not directory.is_absolute():
        continue
    try:
        directory = directory.resolve()
    except OSError:
        continue
    if not path_is_inside(directory, repo):
        trusted_path_entries.append(str(directory))
trusted_path = os.pathsep.join(dict.fromkeys(trusted_path_entries))
safe_help_limit = 5

for ref in prerequisite_refs:
    executable = ref["executable"]
    simple_name = re.fullmatch(r"[A-Za-z0-9_.+-]+", executable) is not None
    resolved = trusted_which(executable) if simple_name else None
    if not simple_name and ("/" in executable or "\\" in executable):
        candidate = (repo / executable).resolve()
        try:
            candidate.relative_to(repo)
            resolved = str(candidate) if candidate.is_file() else None
        except ValueError:
            resolved = None
    if demo:
        resolved = f"demo:{executable}"
    if not resolved:
        add("missing_prerequisite", "warning", "high", f'Documented executable `{executable}` is unavailable', f'{ref["doc"]}: {ref["command"]}', "Install the prerequisite or document where and how it becomes available.")
        continue
    normalized = pathlib.Path(executable).name.lower()
    if verification != "safe-help" or demo or not simple_name or normalized not in safe_help_allowlist:
        continue
    if safe_help_attempts >= safe_help_limit:
        add("safe_help_limit_reached", "watch", "high", "Additional safe-help checks were skipped", f"limit={safe_help_limit}; prerequisites={len(prerequisite_refs)}", "Run a focused manual check for the remaining CLIs or reduce the documented command set.")
        continue
    argv = [resolved]
    subcommand = ref.get("subcommand", "")
    if subcommand in safe_subcommands.get(normalized, set()):
        argv.append(subcommand)
    argv.append("-h" if normalized == "git" and len(argv) > 1 else "--help")
    child_env = {
        key: os.environ[key]
        for key in ("COMSPEC", "LANG", "LC_ALL", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "WINDIR")
        if key in os.environ
    }
    child_env["PATH"] = trusted_path
    child_env.update({"CI": "1", "NO_COLOR": "1", "PAGER": "cat", "GIT_PAGER": "cat"})
    safe_help_attempts += 1
    try:
        with tempfile.TemporaryDirectory(prefix="documentation-contract-referee-") as neutral_cwd:
            completed = subprocess.run(argv, cwd=neutral_cwd, env=child_env, stdin=subprocess.DEVNULL, text=True, capture_output=True, timeout=5, check=False)
        safe_help_checks += 1
    except (OSError, subprocess.TimeoutExpired) as exc:
        add("safe_help_unavailable", "watch", "medium", f'Could not inspect safe help for `{executable}`', f'{ref["doc"]}: {type(exc).__name__}', "Use static verification or inspect the CLI help manually.")
        continue
    help_text = (completed.stdout + "\n" + completed.stderr)[:200_000]
    if completed.returncode != 0:
        add("safe_help_unavailable", "watch", "medium", f'Safe help for `{executable}` exited with code {completed.returncode}', f'{ref["doc"]}: {" ".join(pathlib.Path(part).name if index == 0 else part for index, part in enumerate(argv))}', "Use static verification or inspect the CLI help manually.")
        continue
    for flag in ref.get("flags", []):
        if flag not in help_text:
            add("flag_not_in_safe_help", "warning", "medium", f'Documented flag `{flag}` was not found in current CLI help', f'{ref["doc"]}: {ref["command"]}', "Update the flag or verify it against the installed CLI version.")

rank = {"error": 0, "warning": 1, "watch": 2}
findings.sort(key=lambda item: (rank[item["severity"]], item["rule"], item["evidence"]))
all_count = len(findings)
selected = findings[:maximum]
verdict = "contract_broken" if any(f["severity"] == "error" for f in findings) else ("review_required" if findings else "contract_holds")
print(json.dumps({
    "ok": True,
    "verdict": verdict,
    "findings": selected,
    "finding_count": all_count,
    "omitted_count": max(0, all_count - len(selected)),
    "checked": {
        "documents": len(docs["docs"]),
        "documented_scripts": len(docs["script_refs"]),
        "documented_make_targets": len(docs["make_refs"]),
        "documented_just_recipes": len(docs["just_refs"]),
        "documented_commands": len(docs["script_refs"]) + len(docs["make_refs"]) + len(docs["just_refs"]),
        "local_links": len(docs["link_refs"]),
        "anchors": sum(1 for item in docs["link_refs"] if item.get("fragment")),
        "versions": len(docs["versions"]),
        "environment_variables": len(docs["env_refs"]),
        "package_managers": len({item["manager"] for item in docs["managers"]}),
        "prerequisites": len(prerequisite_refs),
        "safe_help_attempts": safe_help_attempts,
        "safe_help_checks": safe_help_checks,
        "total_claims": primary_claim_count,
        "manifest_scripts": len(state["scripts"]),
    },
    "read_only": True,
    "verification_mode": verification,
    "documented_commands_executed": 0,
    "demo": demo or None,
}, sort_keys=True))
