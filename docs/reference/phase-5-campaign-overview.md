# Current scientific campaign overview

This page summarizes the current finder candidate and unresolved scientific
work, as recorded on **12 September 2026**. Phase 5 remains part of immutable
campaign names; it no longer defines the size of a release. See
[release status](release-status.md) for current public capabilities and the
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
for merge, experimental release and later qualification tasks.

## Current candidate and evidence

Composition **v15**, science commit `73ab5af...`, includes the Gaussian-validity
repair and the approved F4 filtered-response correction. The
[frozen identity review](https://github.com/gemmadanks/hebog/blob/main/config/contracts/phase-5-filtered-response-domain-repair-identity-review.json)
binds its source, configuration and validation. It remains
`development-unqualified`.

| Evidence | What it establishes | Limit |
| --- | --- | --- |
| Focused F4 fixtures and Serial/existing-Dask checks | Each significance plane is paired with its physical filtered response; finite-positive validation, thresholds and original-pixel measurement ownership are retained. | Mechanism and execution correctness, not population parity. |
| Portable suite and frozen equivalence checks | 3,992 portable tests, 95.2963% branch-aware coverage and 27 frozen equivalence tests pass for the repair. | Does not replace candidate-bound held-out qualification or the full platform matrix. |
| Exact previously failing input | One complete public capture succeeds after F4. | No scientific evaluation or parity verdict from that control. |
| Result-neutral 24-input public screen | Captures, native product reading, evaluation and aggregation complete; two Serial/Dask scientific digests agree exactly. | All 1,187 point rows are unchanged: 1,138 within margin, 49 beyond. No powered confidence-bound pass is claimed. |
| V15 cumulative replay | The latest recorded operational snapshot has the isolated two-worker run active; no terminal verdict is recorded. | Partial progress is not scientific evidence. Do not inspect partial science or launch a duplicate. |

The running replay's admitted scope is 2,400 current-Hebog Serial captures,
12 existing-Dask comparisons, 8,000 reused comparator records and one atomic
terminal evaluation, with no new incumbent or external finder execution.
The exact admission, identities, runtime location and progress are maintained
in [LOG.md](https://github.com/gemmadanks/hebog/blob/main/LOG.md) and the existing
monitor. This documentation refresh does not independently establish live
process health.

## What still needs a decision

The screen retains **37 compact and 12 Continuum point-estimate warnings**.
Compact measurement/uncertainty, faint extended fragmentation and mask/flux
tails remain scientific risks. The independent
[follow-up review](phase-5-v13-followup-review.md) explains the mechanisms and
negative controls; its earlier candidate-specific observations are not new
v15 results. Broader faint-association work (F2) remains deferred pending
terminal severity review.

Gaussian-validity and filtered-response repairs are implemented and tested.
Their fixture passes do not establish that every catalogue measurement or
association is scientifically correct. Review the complete terminal against
truth, compact first and Continuum second, and account for every failed or
underpowered comparison and any known public witness.

The agreed
[severity policy](phase-5-v13-followup-review.md#later-decision-final-campaign-then-development-closeout)
blocks development closeout for serious operational/public-contract defects
or material loss of ordinary Rapthor-critical behaviour. Difficult faint
morphology and inconclusive comparisons can be deferred only with their
impact explained. Uncertain serious impact requires bounded triage and human
disposition. A confirmed incorrect supported output remains a release blocker.

After terminal verification and severity review, close development if no
serious issue remains and prioritize complete-path profiling and bounded
scalability work. Scientific readiness still needs candidate-bound
parity/retention, fresh evidence and independent acceptance. The new
experimental-release sequence does not change those scientific verdicts.

## Where the historical evidence lives

Earlier compact/continuum qualifications, public-data failures, source-aligned
sentinels and cumulative failures apply to their exact frozen candidates.
V14's terminal is a capture exception, not a scientific verdict. Failed or
underpowered decisions are never rescored, erased or transferred to a repaired
candidate; an old uncertainty exception is not inherited by v15.

Use the [execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md),
[immutable contracts](https://github.com/gemmadanks/hebog/tree/main/config/contracts)
and dated evidence reviews for exact decisions and reproduction identities.
The former chronological overview is available in
[Git history](https://github.com/gemmadanks/hebog/blob/0ce253cf26a7954a58dc9a211eb01d8502e69025/docs/reference/phase-5-campaign-overview.md).
Update this page by replacing current conclusions; append material history to
the log rather than adding competing “latest” sections here.
