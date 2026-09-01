import base64, json, pathlib, re, shlex, sys, urllib.parse

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
