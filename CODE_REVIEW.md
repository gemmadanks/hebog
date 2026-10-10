# Code Review Guide

Use this guide for human or agent review of uncommitted changes, commits, and
pull requests. Establish the intended outcome from the request, issue, or work
plan before judging the implementation.

## Self-review before a pull request

The author reviews every change against this guide before pushing it or
handing it off, and fixes what the review finds; external reviewers should
not find anything this guide describes. Review after the tests pass, as a
reviewer who did not write the change: read the whole diff again rather than
recalling what it was meant to do. For a change to a public contract, schema,
input boundary or scientific behaviour, add an independent pass where one is
available (a second person, or a separate agent given only the request, the
diff and this guide), and fix its findings too.

Fixing a finding changes the diff, so rerun the checks the fix invalidates
and review the fix itself. A finding answered by an existing decision rather
than a change (a deferred risk, an accepted limitation) still goes in the
pull request description with where the decision is recorded, so a reviewer
does not have to rediscover it.

Review the proposed squash message against `AGENTS.md`: it must preserve the
problem, outcome, rationale, consequential decisions or breaking changes,
validation and omissions, and relevant issue, ADR and evidence references
for future developers. The human merging the PR checks the actual message;
do not rely on branch messages surviving the squash. `LOG.md` is a historical
archive and new entries are not required.

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
4. Check that every guarantee the change states in a docstring, guide, or
   contract has a code path that enforces it. A promise with no mechanism
   behind it is a finding in its own right, whether the fix is the mechanism
   or the wording.
5. For every fact the change alters (a limit, count, default, schema version,
   rule, status, or plan position), search the whole repository for
   statements of the old fact and correct each one. Search every spelling
   (`3,000`, `3000`, `3,000 px`, `3,000-pixel`), the fact's name, and the
   claims that depend on it ("the next tier", "no case takes that path"),
   not only the phrasing the change replaced. Tables, notebooks, docstrings,
   error messages, the README, and the plan state facts too. Then read each
   user-facing page that describes the changed behaviour from start to
   finish: a checklist that is still true word for word can be incomplete
   once a rule is added or a value becomes optional.
6. When the change widens an envelope (a size limit, an accepted input
   form, a supported configuration), re-derive every declared limit or
   exception that scales with it at the new bound. A limit that the widening
   makes reachable is a finding unless the plan or an accepted decision
   records it, and even then its cost at the new bound belongs where users
   read the envelope.
7. Follow each new or changed field, record, module, or stage through
   everything that enumerates its siblings: schemas and their versions,
   configuration and manifest models, serializers and identity hashes, CLI
   and worker arguments, fingerprints and registries, and documentation
   tables and fixtures. A `cast`, `Any`, `# type: ignore`, `getattr`
   default, or broad `except` that the change adds is a finding until it is
   shown not to hide a type or case the rest of the system does not admit.
8. At every input boundary, list the malformed forms of each value read
   (missing, blank, non-finite, fractional where an integer or code is
   expected, out of range, wrong type, a shape that broadcasts, an unknown
   identifier) and confirm each reaches the boundary's typed, specific
   error. Silent conversions such as `round`, `int`, `astype`, broadcasting,
   and `dict.get` defaults are where malformed input passes as valid.
9. Where a quantity crosses to or from another tool or standard (PyBDSF,
   Rapthor, LSMTool, Astropy, FITS WCS), confirm its convention from that
   tool's source or documentation rather than its name: units, great-circle
   or coordinate angle, sign, pixel origin, axis order, and frame.
10. Run the narrowest command that can confirm or refute a suspected problem.
11. Check that generated files, lockfiles, and release-managed files changed
    only when the task requires them.
12. Confirm dependencies still point inward: scientific algorithms and domain
    records must not acquire workflow, adapter, concrete-scheduler, global
    state, or import-time I/O dependencies.
13. Look for unclear domain names, mixed abstraction levels, hidden side
    effects, boolean mode proliferation, speculative extension frameworks,
    accidental duplication, and complexity not justified by scientific or
    performance evidence.
14. For substantial custom infrastructure or a newly implemented generally
    available capability, confirm established standards, the standard
    library, and mature maintained libraries were considered. Require a
    concrete reason when scientific, performance, scalability, portability,
    security, licence, or dependency-cost constraints make custom code the
    better choice.
15. For a new executor, store, adapter, or workflow integration, confirm the
    existing public API or a narrow protocol supports it without conditionals
    spreading through unrelated scientific modules.
16. Confirm each changed behaviour has a focused test that would fail for the
    intended reason if that behaviour were removed. Look for normal, boundary,
    failure, short-circuit, and regression cases rather than line execution
    without meaningful assertions. A test's name and docstring say what it
    asserts. For tiled or sharded code, include an object whose bounds end
    exactly on a core edge and whose support reaches past its bounds; a
    one-tile run never exercises either.
17. Where one contract covers several implementations or entry points, check
    the whole behaviour-by-entry-point matrix required by `AGENTS.md`, not the
    entry point the change was written around. Check platform-dependent
    comparisons the same way: the development machine never runs Windows.
18. Run `just coverage` for production changes. Inspect branch-aware project
    coverage, changed-file misses, and the Codecov diff/patch report when
    available. The 80% project floor does not excuse a poorly covered patch.
    Treat reduced project or patch coverage as a finding unless an explicit
    human-approved exception explains the risk and follow-up.
19. Reject coverage gaming, including weakened assertions, inappropriate
    `pragma: no cover` markers or omit rules, tests coupled to implementation
    details only to execute a line, and deletion of meaningful cases.
20. For native code, verify the recorded profile and end-to-end gate, FFI array
    ownership and copy contract, interpreter release, thread budget, exception
    safety, readable serial oracle, scientific parity, safety tooling, license,
    and complete supported wheel matrix. Reject a kernel-only speedup that is
    immaterial end to end.
21. Finish with `just check` when proportional to the change, plus the
    additional commands required by `AGENTS.md`.

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
cause. A stale statement elsewhere in the repository that the change makes
false is caused by the change, even though the change does not touch it.

## Review output

Present findings first, ordered by priority. Then state:

- assumptions or questions that limit confidence;
- checks run and their results;
- project and patch coverage results for production changes; and
- residual risks or approved coverage gaps.

If there are no findings, say so explicitly and still report checks and
remaining test or review gaps. A clean review means no actionable issue was
found; it does not claim the change is risk-free.

In a self-review, fix each finding before handoff and report what was fixed,
what each fix was checked with, and any finding left to an existing decision.
