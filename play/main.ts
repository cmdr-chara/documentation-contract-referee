/**
 * Documentation Contract Referee
 *
 * Read-only referee for documentation claims against repository evidence.
 *
 * @rote-frontmatter
 * ---
 * name: documentation-contract-referee
 * version: 0.2.0
 * description: 'Referees executable claims in README files and runbooks against repository evidence: commands, prerequisites, Markdown anchors, package scripts, Make targets, Just recipes, package manager, versions, and environment templates. Returns a compact contract verdict with coverage, evidence, and fixes. Credential-free and never executes copied documentation commands.'
 * provenance:
 *   author: cmdr-chara
 * metadata:
 *   rote_version: 0.77.0
 *   version: 0.2.0
 *   status: released
 *   kind: atomic
 *   execution_model: steps_with_presentation
 *   flow_type: parallel
 *   format: typescript
 *   requires_sessions: false
 *   discoverability:
 *     tags:
 *     - domain-devtools
 *     - job-documentation-contracts
 *     - job-release-readiness
 *     - audience-developers
 *     - effect-read-only
 * parameters:
 * - name: repo_path
 *   param_type: string
 *   required: false
 *   default: .
 *   description: Local repository path to inspect.
 *   example: .
 *   valid_values: null
 * - name: docs_paths
 *   param_type: string
 *   required: false
 *   default: README.md,docs
 *   description: Comma-separated repository-relative documentation files or directories.
 *   example: README.md,docs,runbooks
 *   valid_values: null
 * - name: max_findings
 *   param_type: integer
 *   required: false
 *   default: '3'
 *   description: Maximum number of prioritized findings to display, from 1 to 10.
 *   example: '3'
 *   valid_values: null
 * - name: baseline_sha
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: Optional git commit used to flag executable-contract changes made without documentation changes.
 *   example: HEAD~1
 *   valid_values: null
 * - name: verification
 *   param_type: string
 *   required: false
 *   default: static
 *   description: Use static checks only, or execute reconstructed allow-listed CLI help forms without running copied commands.
 *   example: safe-help
 *   valid_values:
 *   - static
 *   - safe-help
 * - name: demo
 *   param_type: string
 *   required: false
 *   default: ''
 *   description: Optional deterministic built-in demonstration; leave empty to inspect repo_path.
 *   example: stale
 *   valid_values:
 *   - ''
 *   - coherent
 *   - stale
 * presentation_fixtures:
 *   validate_input: resources/presentation-fixtures/validate_input/fixture.yaml
 *   scan_documentation: resources/presentation-fixtures/scan_documentation/fixture.yaml
 *   scan_repository: resources/presentation-fixtures/scan_repository/fixture.yaml
 *   judge_contract: resources/presentation-fixtures/judge_contract/fixture.yaml
 * steps:
 *   validate_input:
 *     type: process.exec
 *     timeout_ms: 15000
 *     argv:
 *     - python3
 *     - '@resource{validate.py}'
 *     - $repo_path
 *     - $docs_paths
 *     - $max_findings
 *     - $baseline_sha
 *     - $verification
 *     - $demo
 *   scan_documentation:
 *     type: process.exec
 *     timeout_ms: 30000
 *     depends_on:
 *     - validate_input
 *     argv:
 *     - python3
 *     - '@resource{scan_docs.py}'
 *     - '@validate_input{$.stdout.text | fromjson | .repo}'
 *     - '@validate_input{$.stdout.text | fromjson | .docs_spec}'
 *     - '@validate_input{$.stdout.text | fromjson | .demo}'
 *   scan_repository:
 *     type: process.exec
 *     timeout_ms: 30000
 *     depends_on:
 *     - validate_input
 *     argv:
 *     - python3
 *     - '@resource{scan_repo.py}'
 *     - '@validate_input{$.stdout.text | fromjson | .repo}'
 *     - '@validate_input{$.stdout.text | fromjson | .baseline_sha}'
 *     - '@validate_input{$.stdout.text | fromjson | .demo}'
 *   judge_contract:
 *     type: process.exec
 *     timeout_ms: 30000
 *     depends_on:
 *     - scan_documentation
 *     - scan_repository
 *     argv:
 *     - python3
 *     - '@resource{assess.py}'
 *     - '@validate_input{$.stdout.text | fromjson | .repo}'
 *     - '@scan_documentation{$.stdout.text | fromjson | .payload}'
 *     - '@scan_repository{$.stdout.text | fromjson | .payload}'
 *     - '@validate_input{$.stdout.text | fromjson | .max_findings}'
 *     - '@validate_input{$.stdout.text | fromjson | .verification}'
 *     - '@validate_input{$.stdout.text | fromjson | .demo}'
 * ---
 */

const { FlowOutput, isProcessExecBody, loadPresentationContext, stepName } = await import("__ROTE_PRESENTATION_SDK__");
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
