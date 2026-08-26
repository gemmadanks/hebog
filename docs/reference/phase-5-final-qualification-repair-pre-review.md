# Phase 5 final-qualification evaluation-repair pre-review

## Decision

Preserve the sealed qualification campaign and repair only the evaluation
composition. Do not rerun a finder, modify a scientific product, reinterpret a
gate, or edit the originally approved compiler in place.

The machine-readable pre-review is
`config/contracts/phase-5-final-qualification-evaluation-repair-pre-review.json`,
SHA-256
`8cff6163c4f0ebc3325b0c9c801e099e198ae8bb43b070618e2e0a914e546917`.
It authorizes nothing by itself. Its implementation, compilation, evaluation,
optimization, tuning, rescoring, and campaign-reexecution flags are all false.

## Evidence boundary

The one approved campaign sealed successfully with these operational
identities:

| Evidence | Identity |
| --- | --- |
| Campaign | `benchmark-results/phase-5/final-qualification-comparison/campaign.json` |
| Campaign SHA-256 | `4badb8e1bb8b141c654ede168d6e75e93514dee1ae41e4ccad710fefde3f3e08` |
| Request SHA-256 | `eebb6d793b0ee4532db2393bf06468df53dbc9521092cc8fb6e2340be7194726` |
| Inputs | 1,688 |
| Finder runs | 8,440 |
| Frozen identity review | `42ad623779c381ae69532af1cdc3e9063f7229154f28209e2c1da36199280197` |
| Frozen compiler | `c2b7f3ac3b072ba1c250cd27c917495cab3ba517cfb86a9102d06c763b66b165` |
| Frozen evaluator | `558e29574287aef6bee348fb37c329b7dab2f115ff42c481d3a1019d3f713560` |

The frozen compiler was invoked once. It failed while validating the request
identity, before the verifier entered its input/result loop. It therefore read
no scientific product and wrote neither
`final-qualification-analysis.json` nor
`final-qualification-decision.json`. The qualification result remains unknown;
successful campaign execution is not a scientific pass.

The raw campaign must remain intact until an authorized compiler has verified
and compiled it. Removing its inputs or results now would destroy the only
approved one-look evidence and force a new scientific decision about whether
another campaign is permissible.

## Root cause

The compiler inherits its proven science machinery through three compatibility
layers:

```text
final qualification
  -> recovery compiler
  -> post-failure compiler
  -> terminal verifier
```

The final layer correctly assigned final-qualification loaders to the
recovery module's `_HELPERS`. During configuration, however, the recovery
compiler immediately populated the post-failure layer from its older
`_COMPAT_HELPERS`. That stale map still selected
`load_recovery_execution_decision`. The post-failure JSON adapter consequently
sent the final-qualification decision to the recovery schema and raised:

```text
ValueError: recovery decision fields changed
```

A no-science diagnostic exercised this exact runtime seam. The frozen
composition installed the recovery loader. Supplying the complete final
aliases at the inherited compatibility boundary installed
`load_final_qualification_execution_decision`, admitted the approved decision,
and retained the `Literal[1688]`/`Literal[8440]` request model. It did not read,
compile, or score campaign products.

The existing smoke test missed this defect because it loaded the prospective
compiler and evaluator contracts but never asked the configured terminal's
actual JSON adapter to load the final decision.

## Options considered

| Option | Decision | Reason |
| --- | --- | --- |
| Rerun the campaign | Reject | The campaign is complete, and the approval authorized one execution only. A rerun adds no information about this procedural defect. |
| Edit the frozen compiler in place | Reject | It would erase the checksum identity of the program that failed and invalidate the historical execution review. |
| Patch globals from an ad hoc command | Reject | An unbound runtime patch would not be reproducible or reviewable and could silently change more than the failed seam. |
| Treat the campaign as passed operationally | Reject | A sealed raw campaign has not passed any scientific gate until the frozen analysis and evaluator complete. |
| Add checksummed evaluation-only repair programs around the frozen composition | Recommend | This retains the original evidence and program identities while making the one procedural adaptation explicit, tested, and separately authorized. |

## Recommended repair

### 1. Preserve the frozen composition

Keep the original compiler, evaluator, protocol, endpoint registry, execution
decision, campaign, request, candidate products, and runtime identities
byte-for-byte unchanged. The repair must load these as checksum-bound
dependencies rather than replacing them.

### 2. Add an evaluation-only repair compiler

Add
`scripts/validation/compile_phase5_final_qualification_repair.py`. It should:

- refuse to run without a separate named authorization bound to the sealed
  campaign and its own exact checksum;
- clone the final helper map and install complete post-failure and recovery
  aliases at both inherited `_HELPERS` and `_COMPAT_HELPERS` seams;
- call the frozen compiler's existing science function with the frozen
  compiler path and frozen endpoint registry;
- retain the intended frozen analysis schema and add explicit repair
  provenance; and
- write the existing analysis path once using exclusive creation.

The wrapper must not add a second scientific implementation. Its only allowed
behavioural difference is selecting the final-qualification protocol,
decision, registry, and request models at the already intended seam.

### 3. Add an evaluation-only repair evaluator

Add
`scripts/validation/evaluate_phase5_final_qualification_repair.py`. It should
verify the repair provenance and the frozen analysis identities, delegate
scientific scoring to the frozen evaluator's pure decision function, and add
the repair review/authorization checksums to the write-once terminal decision.
It must not change endpoint selection, confidence intervals, margins,
absolute thresholds, compact conjunction, runtime ordering, or decision
precedence.

### 4. Exercise the real failing seam

The regression must configure the actual inherited terminal boundary and
prove that:

- the final protocol, registry, and approved decision load through the JSON
  adapter that failed;
- `load_final_qualification_execution_decision`, not the recovery loader, is
  installed;
- the request models retain exactly 1,688 images and 8,440 runs;
- a recovery-shaped or otherwise changed decision fails closed;
- the frozen original files remain unchanged; and
- repair entry points reject missing approval, changed evidence, existing
  outputs, campaign reexecution, optimization, tuning, rescoring, and any
  science or gate amendment.

Synthetic records are sufficient for failure-path tests. Tests must not read
raw qualification products or execute the compiler.

### 5. Freeze two separate approval boundaries

After implementation and complete validation, create a pending repair-identity
review binding:

- the implementation commit and tree;
- the repair compiler and evaluator paths and SHA-256 values;
- the sealed campaign and request SHA-256 values;
- the frozen compiler, evaluator, endpoint registry, evaluation contract,
  execution decision, and identity review;
- the absent analysis and decision outputs; and
- explicit false values for campaign execution, scientific changes, tuning,
  rescoring, cutover, and release.

A second named decision may then authorize exactly one compilation and one
evaluation of campaign `4badb8e1...`. The implementation approval described
below does not grant that execution authority.

## Approval requested now

The requested approval is limited to implementing and validating the repair
programs and freezing their exact identities. Suggested wording is:

> I approve the Phase 5 final-qualification evaluation-repair pre-review
> SHA-256
> `8cff6163c4f0ebc3325b0c9c801e099e198ae8bb43b070618e2e0a914e546917`
> and its recommendations. This authorizes implementation and validation of
> the evaluation-only repair and freezing of exact repair identities against
> existing campaign
> `4badb8e1bb8b141c654ede168d6e75e93514dee1ae41e4ccad710fefde3f3e08`.
> It does not authorize compilation, evaluation, campaign reexecution,
> optimization, tuning, rescoring, cutover, or release.

After that implementation is committed, a new exact-identity review will be
presented for a separate named compilation/evaluation approval.

## Implemented repair and pending execution review

The implementation-only approval was recorded on 2026-08-26. Repair compiler
commit `b6ce3cdd49d3e51f2d1437cea3d4d4a4d79d056c` passes the real inherited
JSON-seam regression and delegates science compilation and evaluation to the
byte-exact frozen programs. Neither campaign science nor a write-once output
was opened while implementing or validating it.

The pending machine identity review is
`config/contracts/phase-5-final-qualification-evaluation-repair-review.json`,
SHA-256
`b69b2eaa4b7d00b12314e0a7d753c22843778111ac4f0d1214dc3e1a790e2305`.
It binds:

- sealed campaign `4badb8e1...` and request `eebb6d79...`;
- implementation commit `b6ce3cdd...` and tree `fa7e1a07...`;
- repair compiler `42ac2a96...` and evaluator `f4396a8a...`;
- the byte-exact frozen compiler, evaluator, protocol, population, registry,
  evaluation contract, execution decision, and identity review;
- candidate `9062664...`, source tree `e4307246...`, configuration
  `0e5dde51...`, and the unchanged four runtime identities; and
- absent analysis, decision, and execution-authorization records.

Every authorization flag in that review is false. The review does not permit
the repair programs to run. A suitable separate approval is:

> I approve the Phase 5 final-qualification evaluation repair bound to
> identity review SHA-256
> `b69b2eaa4b7d00b12314e0a7d753c22843778111ac4f0d1214dc3e1a790e2305`
> and its exact repair and frozen identities. This authorizes exactly one
> compilation and one evaluation of existing sealed campaign
> `4badb8e1bb8b141c654ede168d6e75e93514dee1ae41e4ccad710fefde3f3e08`.
> It does not authorize campaign reexecution, optimization, tuning,
> rescoring, cutover, or release.
