import base64, json, pathlib, re, sys

repo = pathlib.Path(sys.argv[1]).resolve()
requested = [part for part in sys.argv[2].split(",") if part]
files = []
def inside(candidate):
    resolved = candidate.resolve()
    try:
        resolved.relative_to(repo)
        return resolved
    except ValueError:
        return None
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
script_refs, make_refs, just_refs, link_refs, managers, versions, env_refs = [], [], [], [], [], [], []
fence = re.compile(r"```[^\n]*\n(.*?)```", re.S)
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
    for target in link.findall(text):
        target = target.strip().split()[0].strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        clean = target.split("#", 1)[0].split("?", 1)[0]
        if clean:
            link_refs.append({"doc": rel, "target": clean})
    blocks = fence.findall(text)
    code = "\n".join(blocks)
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
}
packed = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
print(json.dumps({"ok": True, "payload": packed, "documents_scanned": len(files)}, sort_keys=True))
