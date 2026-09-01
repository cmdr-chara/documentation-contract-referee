from __future__ import annotations

from pathlib import Path


VALIDATE_SCRIPT = r'''import json, pathlib, subprocess, sys

repo_arg, docs_spec, max_arg, baseline, verification, demo = sys.argv[1:7]
repo = pathlib.Path(repo_arg).expanduser().resolve()
if not repo.is_dir():
    print(f"repository path is not a directory: {repo}", file=sys.stderr)
    raise SystemExit(2)
try:
    maximum = int(max_arg)
except ValueError:
    print("max_findings must be an integer", file=sys.stderr)
    raise SystemExit(2)
if maximum < 1 or maximum > 10:
    print("max_findings must be between 1 and 10", file=sys.stderr)
    raise SystemExit(2)
if verification not in {"static", "safe-help"}:
    print("verification must be static or safe-help", file=sys.stderr)
    raise SystemExit(2)
if demo not in {"", "coherent", "stale"}:
    print("demo must be empty, coherent, or stale", file=sys.stderr)
    raise SystemExit(2)
requested = [part.strip() for part in docs_spec.split(",") if part.strip()]
if not requested:
    print("docs_paths must contain at least one repository-relative path", file=sys.stderr)
    raise SystemExit(2)
safe = requested if demo else []
if not demo:
    for item in requested:
        candidate = (repo / item).resolve()
        try:
            candidate.relative_to(repo)
        except ValueError:
            print(f"docs path escapes repository: {item}", file=sys.stderr)
            raise SystemExit(2)
        if candidate.exists():
            safe.append(item)
    if not safe:
        print("none of the requested documentation paths exists", file=sys.stderr)
        raise SystemExit(2)
if baseline and not demo:
    check = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", f"{baseline}^{{commit}}"],
        text=True, capture_output=True, check=False,
    )
    if check.returncode:
        print(f"baseline_sha is not a commit in this repository: {baseline}", file=sys.stderr)
        raise SystemExit(2)
print(json.dumps({
    "ok": True,
    "repo": str(repo),
    "docs_spec": ",".join(safe),
    "max_findings": maximum,
    "baseline_sha": baseline,
    "verification": verification,
    "demo": demo,
}, sort_keys=True))
'''


SCAN_DOCS_SCRIPT = r'''import base64, json, pathlib, re, shlex, sys, urllib.parse

repo = pathlib.Path(sys.argv[1]).resolve()
requested = [part for part in sys.argv[2].split(",") if part]
demo = sys.argv[3]
files = []

def inside(candidate):
    resolved = candidate.resolve()
    try:
        resolved.relative_to(repo)
        return resolved
    except ValueError:
        return None

def command_refs(code, doc):
    refs = []
    builtins = {"cd", "echo", "export", "printf", "read", "set", "source", "test", "true", "false"}
    wrappers = {"command", "env", "sudo", "time"}
    for raw in code.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "//")):
            continue
        line = re.sub(r"^\$\s+", "", line)
        for segment in re.split(r"\s*(?:&&|\|\||;)\s*", line):
            if not segment:
                continue
            try:
                tokens = shlex.split(segment, posix=True)
            except ValueError:
                continue
            while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
                tokens.pop(0)
            while tokens and tokens[0] in wrappers:
                tokens.pop(0)
                while tokens and tokens[0].startswith("-"):
                    tokens.pop(0)
            if not tokens or tokens[0] in builtins:
                continue
            executable = tokens[0]
            subcommand = next((token for token in tokens[1:] if not token.startswith("-") and "=" not in token), "")
            flags = sorted({token.split("=", 1)[0] for token in tokens[1:] if token.startswith("-") and token != "-"})
            refs.append({
                "doc": doc,
                "command": segment[:240],
                "executable": executable,
                "subcommand": subcommand,
                "flags": flags,
            })
    return refs

if demo:
    coherent = demo == "coherent"
    payload = {
        "docs": ["demo/README.md"],
        "script_refs": [{"doc": "demo/README.md", "manager": "npm", "script": "build"}],
        "make_refs": [],
        "just_refs": [],
        "link_refs": [{
            "doc": "demo/README.md",
            "target": "docs/setup.md" if coherent else "docs/missing.md",
            "fragment": "install" if coherent else "",
            "demo_exists": coherent,
            "demo_anchors": ["install"] if coherent else [],
        }],
        "managers": [{"doc": "demo/README.md", "manager": "npm" if coherent else "pnpm"}],
        "versions": [{"doc": "demo/README.md", "version": "1.2.0" if coherent else "2.0.0"}],
        "env_refs": [{"doc": "demo/README.md", "name": "API_URL"}],
        "prerequisite_refs": [{
            "doc": "demo/README.md",
            "command": "npm run build" if coherent else "pnpm run build",
            "executable": "npm" if coherent else "pnpm",
            "subcommand": "run",
            "flags": [],
        }],
    }
    packed = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    print(json.dumps({"ok": True, "payload": packed, "documents_scanned": 1}, sort_keys=True))
    raise SystemExit(0)

for item in requested:
    path = inside(repo / item)
    if path is None:
        continue
    if path.is_file() and path.suffix.lower() in {".md", ".mdx"}:
        files.append(path)
    elif path.is_dir():
        for candidate in path.rglob("*"):
            safe = inside(candidate)
            if safe is not None and safe.is_file() and safe.suffix.lower() in {".md", ".mdx"}:
                files.append(safe)
files = sorted(set(files))[:500]
script_refs, make_refs, just_refs, link_refs, managers, versions, env_refs, prerequisite_refs = [], [], [], [], [], [], [], []
fence = re.compile(r"```([^\n]*)\n(.*?)```", re.S)
link = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
script_patterns = [
    ("npm", re.compile(r"\bnpm\s+run\s+([\w:.-]+)")),
    ("pnpm", re.compile(r"\bpnpm\s+(?:run\s+)?([\w:.-]+)")),
    ("yarn", re.compile(r"\byarn\s+(?:run\s+)?([\w:.-]+)")),
    ("bun", re.compile(r"\bbun\s+run\s+([\w:.-]+)")),
]
for path in files:
    rel = path.relative_to(repo).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")[:1_000_000]
    for raw_target in link.findall(text):
        target = raw_target.strip().split()[0].strip("<>")
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        path_part, _, fragment = target.partition("#")
        clean = path_part.split("?", 1)[0]
        if clean or fragment:
            link_refs.append({
                "doc": rel,
                "target": urllib.parse.unquote(clean),
                "fragment": urllib.parse.unquote(fragment).lower(),
            })
    blocks = fence.findall(text)
    code = "\n".join(body for _, body in blocks)
    shell_languages = {"", "sh", "bash", "shell", "zsh", "console", "powershell", "pwsh", "cmd", "bat"}
    shell_code = "\n".join(
        body for language, body in blocks
        if (language.strip().lower().split(maxsplit=1) or [""])[0] in shell_languages
    )
    prerequisite_refs.extend(command_refs(shell_code, rel))
    for manager, pattern in script_patterns:
        if re.search(rf"\b{manager}\b", code):
            managers.append({"doc": rel, "manager": manager})
        for match in pattern.finditer(code):
            command = match.group(1)
            if command not in {"install", "i", "ci", "add", "remove", "exec", "dlx"}:
                script_refs.append({"doc": rel, "manager": manager, "script": command})
    for match in re.finditer(r"(?m)^\s*(?:\$\s*)?make\s+([\w.-]+)", code):
        make_refs.append({"doc": rel, "target": match.group(1)})
    for match in re.finditer(r"(?m)^\s*(?:\$\s*)?just\s+([\w.-]+)", code):
        just_refs.append({"doc": rel, "recipe": match.group(1)})
    for match in re.finditer(r"(?im)\b(?:current\s+)?version\s*(?::|is)?\s*v?(\d+\.\d+\.\d+)\b", text):
        versions.append({"doc": rel, "version": match.group(1)})
    for name in sorted(set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", code))):
        if "_" in name:
            env_refs.append({"doc": rel, "name": name})
payload = {
    "docs": [p.relative_to(repo).as_posix() for p in files],
    "script_refs": script_refs,
    "make_refs": make_refs,
    "just_refs": just_refs,
    "link_refs": link_refs,
    "managers": managers,
    "versions": versions,
    "env_refs": env_refs,
    "prerequisite_refs": prerequisite_refs,
}
packed = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
print(json.dumps({"ok": True, "payload": packed, "documents_scanned": len(files)}, sort_keys=True))
'''


SCAN_REPO_SCRIPT = r'''import base64, json, pathlib, re, subprocess, sys

repo = pathlib.Path(sys.argv[1]).resolve()
baseline = sys.argv[2]
demo = sys.argv[3]
if demo:
    coherent = demo == "coherent"
    payload = {
        "scripts": {"build": "tsc"} if coherent else {"test": "node --test"},
        "versions": [{"source": "package.json", "version": "1.2.0" if coherent else "1.0.0"}],
        "locks": {"npm": True, "pnpm": False, "yarn": False, "bun": False},
        "env_names": ["API_URL"],
        "make_targets": [],
        "just_recipes": [],
        "changed": [],
    }
    packed = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    print(json.dumps({"ok": True, "payload": packed, "scripts_found": len(payload["scripts"])}, sort_keys=True))
    raise SystemExit(0)
scripts, versions = {}, []
package = repo / "package.json"
if package.is_file():
    try:
        data = json.loads(package.read_text(encoding="utf-8"))
        scripts = {str(k): str(v) for k, v in data.get("scripts", {}).items()}
        if isinstance(data.get("version"), str):
            versions.append({"source": "package.json", "version": data["version"]})
    except (OSError, json.JSONDecodeError):
        pass
pyproject = repo / "pyproject.toml"
if pyproject.is_file():
    text = pyproject.read_text(encoding="utf-8", errors="replace")[:300_000]
    match = re.search(r"(?m)^version\s*=\s*[\"']([^\"']+)[\"']", text)
    if match:
        versions.append({"source": "pyproject.toml", "version": match.group(1)})
locks = {
    "npm": (repo / "package-lock.json").is_file(),
    "pnpm": (repo / "pnpm-lock.yaml").is_file(),
    "yarn": (repo / "yarn.lock").is_file(),
    "bun": (repo / "bun.lockb").is_file() or (repo / "bun.lock").is_file(),
}
env_names = set()
for name in (".env.example", ".env.sample", ".env.template"):
    path = repo / name
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", line)
            if match:
                env_names.add(match.group(1))
make_targets = set()
makefile = repo / "Makefile"
if makefile.is_file():
    for line in makefile.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*):(?:\s|$)", line)
        if match:
            make_targets.add(match.group(1))
just_recipes = set()
justfile = repo / "justfile"
if justfile.is_file():
    for line in justfile.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^([A-Za-z][A-Za-z0-9_-]*)(?:\s+[^:=]+)?\s*:(?:\s|$)", line)
        if match:
            just_recipes.add(match.group(1))
changed = []
if baseline:
    diff = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only", f"{baseline}..HEAD"],
        text=True, capture_output=True, check=False,
    )
    if diff.returncode == 0:
        changed = [line.strip().replace("\\", "/") for line in diff.stdout.splitlines() if line.strip()]
payload = {
    "scripts": scripts,
    "versions": versions,
    "locks": locks,
    "env_names": sorted(env_names),
    "make_targets": sorted(make_targets),
    "just_recipes": sorted(just_recipes),
    "changed": changed,
}
packed = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
print(json.dumps({"ok": True, "payload": packed, "scripts_found": len(scripts)}, sort_keys=True))
'''


ASSESS_SCRIPT = r'''import base64, json, os, pathlib, re, subprocess, sys, tempfile

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
'''


PRESENTATION = r'''const { FlowOutput, isProcessExecBody, loadPresentationContext, stepName } = await import("__ROTE_PRESENTATION_SDK__");
const out = new FlowOutput();
const ctx = await loadPresentationContext();

const validateStep = ctx.step(stepName("validate_input"));
const docsStep = ctx.step(stepName("scan_documentation"));
const repoStep = ctx.step(stepName("scan_repository"));
const assessStep = ctx.step(stepName("judge_contract"));

let assessment = null;
if (assessStep.outcome.status === "completed" || assessStep.outcome.status === "restored") {
  try {
    const available = ctx.requireAvailable(stepName("judge_contract"));
    if (available.shape === "single" && isProcessExecBody(available.body)) {
      const exit = available.body.status.exit;
      const stdout = available.body.stdout?.text;
      if (exit.kind === "code" && exit.code === 0 && typeof stdout === "string") {
        assessment = JSON.parse(stdout);
      }
    }
  } catch {
    assessment = null;
  }
}
const stageRows = [
  ["validate input", validateStep],
  ["scan documentation", docsStep],
  ["scan repository", repoStep],
  ["judge contract", assessStep],
].map(([label, step]) => {
  const status = step?.outcome?.status ?? "unknown";
  const glyph = status === "completed" || status === "restored" ? "████████" : status === "skipped" ? "░░░░░░░░" : "████░░░░";
  return `  ${glyph}  ${label}  ${status}`;
});

if (!assessment) {
  const human = ["DOCUMENTATION CONTRACT REFEREE", "", ...stageRows, "", "Verdict unavailable: inspect the failed or blocked step and resume the run."].join("\n");
  out.human(human);
  out.summary("Documentation Contract Referee could not produce a verdict");
  out.result({
    ok: false,
    verdict: "unknown",
    findings: [],
    representations: {
      human: "complete for the available failed-stage evidence",
      json: "canonical for the available failed-stage evidence",
      summary: "intentionally lossy — failure status only",
    },
  });
} else {
  const label = assessment.verdict === "contract_holds" ? "CONTRACT HOLDS" : assessment.verdict === "contract_broken" ? "CONTRACT BROKEN" : "REVIEW REQUIRED";
  const findings = Array.isArray(assessment.findings) ? assessment.findings : [];
  const lines = ["DOCUMENTATION CONTRACT REFEREE", label, "", ...stageRows, ""];
  if (findings.length === 0) {
    lines.push("Every checked documentation claim matches the repository evidence.");
  } else {
    findings.forEach((finding, index) => {
      lines.push(`${index + 1}. [${String(finding.severity).toUpperCase()}] ${finding.title}`);
      lines.push(`   Evidence: ${finding.evidence}`);
      lines.push(`   Fix: ${finding.suggested_fix}`);
    });
  }
  if (assessment.omitted_count > 0) {
    lines.push("", `${assessment.omitted_count} lower-priority finding(s) omitted by max_findings.`);
  }
  lines.push("", `Coverage: ${assessment.checked.documents} document(s) · ${assessment.checked.total_claims} claim(s) · ${assessment.checked.documented_commands} command(s) · ${assessment.checked.local_links} link(s) · ${assessment.checked.anchors} anchor(s) · ${assessment.checked.prerequisites} prerequisite(s) · ${assessment.checked.safe_help_checks} safe-help check(s).`);
  lines.push(`Verification: ${assessment.verification_mode}; copied documentation commands executed: ${assessment.documented_commands_executed}.`);
  out.human(lines.join("\n"));
  out.summary(`${label} — ${assessment.finding_count} finding(s); ${assessment.checked.total_claims} claim(s) across ${assessment.checked.documents} document(s)`);
  out.result({
    ...assessment,
    representations: {
      human: "complete — verdict, stage ledger, selected findings, evidence, and fixes",
      json: "canonical — adds coverage, verification mode, omitted count, and read-only marker",
      summary: "intentionally lossy — verdict and counts only",
    },
  });
}
'''


def build() -> str:
    frontmatter = f"""name: documentation-contract-referee
version: 0.2.0
description: 'Referees executable claims in README files and runbooks against repository evidence: commands, prerequisites, Markdown anchors, package scripts, Make targets, Just recipes, package manager, versions, and environment templates. Returns a compact contract verdict with coverage, evidence, and fixes. Credential-free and never executes copied documentation commands.'
provenance:
  author: cmdr-chara
metadata:
  rote_version: 0.77.0
  version: 0.2.0
  status: released
  kind: atomic
  execution_model: steps_with_presentation
  flow_type: parallel
  format: typescript
  requires_sessions: false
  discoverability:
    tags:
    - domain-devtools
    - job-documentation-contracts
    - job-release-readiness
    - audience-developers
    - effect-read-only
parameters:
- name: repo_path
  param_type: string
  required: false
  default: .
  description: Local repository path to inspect.
  example: .
  valid_values: null
- name: docs_paths
  param_type: string
  required: false
  default: README.md,docs
  description: Comma-separated repository-relative documentation files or directories.
  example: README.md,docs,runbooks
  valid_values: null
- name: max_findings
  param_type: integer
  required: false
  default: '3'
  description: Maximum number of prioritized findings to display, from 1 to 10.
  example: '3'
  valid_values: null
- name: baseline_sha
  param_type: string
  required: false
  default: ''
  description: Optional git commit used to flag executable-contract changes made without documentation changes.
  example: HEAD~1
  valid_values: null
- name: verification
  param_type: string
  required: false
  default: static
  description: Use static checks only, or execute reconstructed allow-listed CLI help forms without running copied commands.
  example: safe-help
  valid_values:
  - static
  - safe-help
- name: demo
  param_type: string
  required: false
  default: ''
  description: Optional deterministic built-in demonstration; leave empty to inspect repo_path.
  example: stale
  valid_values:
  - ''
  - coherent
  - stale
presentation_fixtures:
  validate_input: resources/presentation-fixtures/validate_input/fixture.yaml
  scan_documentation: resources/presentation-fixtures/scan_documentation/fixture.yaml
  scan_repository: resources/presentation-fixtures/scan_repository/fixture.yaml
  judge_contract: resources/presentation-fixtures/judge_contract/fixture.yaml
steps:
  validate_input:
    type: process.exec
    timeout_ms: 15000
    argv:
    - python3
    - '@resource{{validate.py}}'
    - $repo_path
    - $docs_paths
    - $max_findings
    - $baseline_sha
    - $verification
    - $demo
  scan_documentation:
    type: process.exec
    timeout_ms: 30000
    depends_on:
    - validate_input
    argv:
    - python3
    - '@resource{{scan_docs.py}}'
    - '@validate_input{{$.stdout.text | fromjson | .repo}}'
    - '@validate_input{{$.stdout.text | fromjson | .docs_spec}}'
    - '@validate_input{{$.stdout.text | fromjson | .demo}}'
  scan_repository:
    type: process.exec
    timeout_ms: 30000
    depends_on:
    - validate_input
    argv:
    - python3
    - '@resource{{scan_repo.py}}'
    - '@validate_input{{$.stdout.text | fromjson | .repo}}'
    - '@validate_input{{$.stdout.text | fromjson | .baseline_sha}}'
    - '@validate_input{{$.stdout.text | fromjson | .demo}}'
  judge_contract:
    type: process.exec
    timeout_ms: 30000
    depends_on:
    - scan_documentation
    - scan_repository
    argv:
    - python3
    - '@resource{{assess.py}}'
    - '@validate_input{{$.stdout.text | fromjson | .repo}}'
    - '@scan_documentation{{$.stdout.text | fromjson | .payload}}'
    - '@scan_repository{{$.stdout.text | fromjson | .payload}}'
    - '@validate_input{{$.stdout.text | fromjson | .max_findings}}'
    - '@validate_input{{$.stdout.text | fromjson | .verification}}'
    - '@validate_input{{$.stdout.text | fromjson | .demo}}'"""
    jsdoc_yaml = "\n".join(" *" if not line else f" * {line}" for line in frontmatter.splitlines())
    return f'''/**
 * Documentation Contract Referee
 *
 * Read-only referee for documentation claims against repository evidence.
 *
 * @rote-frontmatter
 * ---
{jsdoc_yaml}
 * ---
 */

{PRESENTATION}'''


if __name__ == "__main__":
    target = Path(__file__).with_name("play") / "main.ts"
    target.parent.mkdir(exist_ok=True)
    target.write_text(build(), encoding="utf-8", newline="\n")
    resources = target.parent / "resources"
    resources.mkdir(exist_ok=True)
    for name, script in {
        "validate.py": VALIDATE_SCRIPT,
        "scan_docs.py": SCAN_DOCS_SCRIPT,
        "scan_repo.py": SCAN_REPO_SCRIPT,
        "assess.py": ASSESS_SCRIPT,
    }.items():
        (resources / name).write_text(script, encoding="utf-8", newline="\n")
    print(target)
