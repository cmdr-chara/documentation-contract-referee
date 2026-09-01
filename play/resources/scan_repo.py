import base64, json, pathlib, re, subprocess, sys

repo = pathlib.Path(sys.argv[1]).resolve()
baseline = sys.argv[2]
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
