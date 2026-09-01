import json, pathlib, subprocess, sys

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
