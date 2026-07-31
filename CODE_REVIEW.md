# Code Review Guide

Use this guide for human or agent review of uncommitted changes, commits, and
pull requests. Establish the intended outcome from the request, issue, or work
plan before judging the implementation.

## Review priorities

Review in this order:

1. Correctness and regressions
2. Security, privacy, and unsafe data handling
3. Public API and supported-version compatibility
4. Architecture boundaries, maintainability, and extensibility
5. Missing or misleading tests and coverage regressions
6. Packaging, documentation, and operational impact

Do not spend review attention on formatting that Ruff or another configured
tool handles automatically.

## Review method

1. Read the complete diff and inspect relevant surrounding code, not only the
   changed lines.
2. Trace important inputs, outputs, error paths, and platform-dependent paths.
3. Compare behavior with tests, documentation, and public API promises.
4. Run the narrowest command that can confirm or refute a suspected problem.
5. Check that generated files, lockfiles, and release-managed files changed only
   when the task requires them.
6. Confirm dependencies still point inward: scientific algorithms and domain
   records must not acquire workflow, adapter, concrete-scheduler, global
   state, or import-time I/O dependencies.
7. Look for unclear domain names, mixed abstraction levels, hidden side
   effects, boolean mode proliferation, speculative extension frameworks,
   accidental duplication, and complexity not justified by scientific or
   performance evidence.
8. For a new executor, store, adapter, or workflow integration, confirm the
   existing public API or a narrow protocol supports it without conditionals
   spreading through unrelated scientific modules.
9. Confirm each changed behaviour has a focused test that would fail for the
   intended reason if that behaviour were removed. Look for normal, boundary,
   failure, short-circuit, and regression cases rather than line execution
   without meaningful assertions.
10. Run `just coverage` for production changes. Inspect branch-aware project
    coverage, changed-file misses, and the Codecov diff/patch report when
    available. The 80% project floor does not excuse a poorly covered patch.
    Treat reduced project or patch coverage as a finding unless an explicit
    human-approved exception explains the risk and follow-up.
11. Reject coverage gaming, including weakened assertions, inappropriate
    `pragma: no cover` markers or omit rules, tests coupled to implementation
    details only to execute a line, and deletion of meaningful cases.
12. For native code, verify the recorded profile and end-to-end gate, FFI array
   ownership and copy contract, interpreter release, thread budget, exception
   safety, readable serial oracle, scientific parity, safety tooling, license,
   and complete supported wheel matrix. Reject a kernel-only speedup that is
   immaterial end to end.
13. Finish with `just check` when proportional to the change, plus the additional
    commands required by `AGENTS.md`.

## Finding quality

Report only actionable findings caused by the change. Each finding should
include:

- **Priority:** `P0` critical, `P1` high, `P2` normal, or `P3` low
- **Location:** the smallest useful file and line range
- **Impact:** the concrete failure or risk and who or what it affects
- **Evidence:** the execution path, reproduction, test, or repository fact that
  supports the finding
- **Remediation:** a concise direction when the fix is not obvious

Avoid vague warnings, speculative failures without a reachable path, and style
preferences not enforced by the repository. Group findings that share one root
cause.

## Review output

Present findings first, ordered by priority. Then state:

- assumptions or questions that limit confidence;
- checks run and their results;
- project and patch coverage results for production changes; and
- residual risks or approved coverage gaps.

If there are no findings, say so explicitly and still report checks and
remaining test or review gaps. A clean review means no actionable issue was
found; it does not claim the change is risk-free.
