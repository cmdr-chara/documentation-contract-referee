import base64, json, pathlib, sys

repo = pathlib.Path(sys.argv[1]).resolve()
docs = json.loads(base64.b64decode(sys.argv[2]).decode())
state = json.loads(base64.b64decode(sys.argv[3]).decode())
maximum = int(sys.argv[4])
findings = []
seen = set()

def add(rule, severity, confidence, title, evidence, fix):
    key = (rule, title, evidence)
    if key not in seen:
        seen.add(key)
        findings.append({
            "rule": rule, "severity": severity, "confidence": confidence,
            "title": title, "evidence": evidence, "suggested_fix": fix,
        })

for ref in docs["link_refs"]:
    doc = repo / ref["doc"]
    target = (doc.parent / ref["target"]).resolve()
    try:
        target.relative_to(repo)
    except ValueError:
        add("link_outside_repo", "warning", "high", "Documentation link escapes the repository", f'{ref["doc"]} -> {ref["target"]}', "Use a repository-relative target inside the project or an explicit trusted URL.")
        continue
    if not target.exists():
        add("broken_local_link", "error", "high", "Documented local link does not exist", f'{ref["doc"]} -> {ref["target"]}', "Restore the target or update the link to the current path.")

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

rank = {"error": 0, "warning": 1, "watch": 2}
findings.sort(key=lambda item: (rank[item["severity"]], item["rule"], item["evidence"]))
all_count = len(findings)
selected = findings[:maximum]
verdict = "contract_broken" if any(f["severity"] == "error" for f in selected) else ("review_required" if selected else "contract_holds")
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
        "manifest_scripts": len(state["scripts"]),
    },
    "read_only": True,
}, sort_keys=True))
