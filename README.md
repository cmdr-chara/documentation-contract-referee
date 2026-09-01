# Documentation Contract Referee

`Documentation Contract Referee` is a draft Rote Play that judges whether a developer can still trust and execute the claims made by a repository's README files and runbooks. It is designed as a pre-release, pre-merge, and onboarding contract check—not as a general repository health dashboard.

Its question is deliberately narrow: **if someone follows the documentation today, will the repository support what it promises?**

It checks:

- local Markdown links;
- documented npm/pnpm/yarn/bun scripts against `package.json`;
- documented `make` targets against `Makefile` and `just` recipes against `justfile`;
- documented package managers against the committed lockfile;
- explicit documentation versions against root manifests;
- documented environment variables against an existing env template;
- optional Git changes to executable contracts without corresponding Markdown changes.

The Play is read-only. It never executes commands copied from documentation, reads secret values, inspects GitHub/CI health, or modifies the inspected repository. It returns a compact `CONTRACT HOLDS`, `CONTRACT BROKEN`, or `REVIEW REQUIRED` verdict and at most three findings by default, each with repository evidence and a suggested correction.

## Inputs

| Input | Default | Meaning |
|---|---|---|
| `repo_path` | `.` | Local repository path to inspect |
| `docs_paths` | `README.md,docs` | Comma-separated documentation files/directories |
| `max_findings` | `3` | Highest-priority findings to return (1–10) |
| `baseline_sha` | empty | Optional commit for change-without-docs detection |

## Build and verify

Generate the clean `play/main.ts` package from the reviewed step sources and run the local tests:

```bash
python3 build_play.py
python3 -m unittest discover -s tests -v
```

With Rote installed on Linux, macOS, or WSL2:

```bash
rote play lint play/main.ts
rote play run play/main.ts repo_path=. docs_paths=README.md,docs max_findings=3
```

Test both a coherent repository (`CONTRACT HOLDS`) and one with a missing command or broken local link (`CONTRACT BROKEN`) before release.

Two ready-made repositories are included under `examples/coherent` and `examples/stale` for that exact demonstration.

## Publication

The checked-in Play package lives under `play/`. Release status and canonical registry links are recorded here only after the Rote lint, live-run, release, registry push, and readback gates have completed successfully.

- Source: <https://github.com/cmdr-chara/documentation-contract-referee>
- Play: <https://play.modiqo.ai/cmdr-chara/documentation-contract-referee@0.1.0>
- Landing: <https://cmdr-chara.github.io/documentation-contract-referee/>

Run the published version:

```bash
rote play run cmdr-chara/documentation-contract-referee@0.1.0 repo_path=/path/to/repository
```
