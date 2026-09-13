# Current capability and release status

Hebog is **experimental**. The current development finder is scientifically
unqualified and is not a production-ready or default Rapthor backend.
Experimental `0.x` releases deliver tested, useful increments; they do not
assert general PyBDSF equivalence or a complete-workflow speedup. Public APIs
and schemas may change between these releases, with breaking changes recorded
in current documentation and release notes.

This page describes the development branch, not a claim that its latest
candidate is already released. See the
[GitHub releases](https://github.com/gemmadanks/hebog/releases) for published
versions and the
[implementation plan](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md)
for the concrete merge/release checklist.

## What the public finder does today

`hebog.find_sources(request, config, executor)` reads one FITS image and
atomically publishes a catalogue, RMS image, source-support mask and diagnostic
record. Background/noise estimation, compact and multiscale detection,
Gaussian components, associated sources and explicit unavailable measurement
statuses are implemented. Run it with the deterministic `SerialExecutor` or
supply an existing Dask client through `DaskExecutor`.

| Boundary | Current behaviour |
| --- | --- |
| Images | ICRS celestial WCS, `Jy/beam`, valid beam/frequency metadata, two spatial axes with optional singleton leading axes. |
| Size | At most 1,024 pixels along either spatial axis through the public finder. Its terminal composition still materializes a bounded preview plane; larger public inputs are rejected. |
| Profiles | Default `continuum`; explicit `compact` reports `extended-emission-incomplete`. Neither current profile is scientifically qualified. |
| Thresholds | The 5/3-sigma, seven-pixel reference configuration reports `development-unqualified`; custom settings report `custom-unqualified`. Continuum refinement uses the caller's detection threshold when its private 75-sigma trigger would conflict with the caller's island threshold. Caller thresholds and the standard 5/3 policy are unchanged. |
| Invalid/empty measurements | Invalid pixels are excluded. Unavailable noise, fits or uncertainties remain explicit; a noiseless emission image with unavailable RMS is not evidence of an empty sky. |
| Products | Source, Gaussian-component and island populations are distinct. Catalogue JSON/FITS and diagnostics schemas are versions 3/4/8; stale schemas fail clearly. |
| Workflow | One scientific image per request. Full Rapthor true-sky/flat-noise filtering integration, operational qualification and complete-path speed evidence remain work to do. |
| Scale | Bounded stages and Dask foundations exist. The complete public finder has not established 100,000-square or hundreds-of-node support. |

Start with [Find sources](../tutorials/find-sources.md). Do not infer public
large-image support from internal-stage tests or use associated-source rows
as if they were Gaussian-component measurements.

## Evidence and unresolved limitations

The development composition is v18, adding a bounded custom-threshold
interaction repair to the tested Gaussian-fallback admission and
background-boundary repairs. The
latest completed campaign is v15 (`73ab5af...`). Focused repair tests, frozen
small equivalence checks, portable coverage and exact Serial/existing-Dask
checks pass. The earlier bounded public screen completed but retains 49
point-estimate warnings, including compact uncertainty/measurement
and faint extended association, mask and flux-tail risks. It does not provide
powered parity evidence and has not been repeated for v17 or v18.

The current package snapshot also repairs destination aliases and failure
rollback in the lower-level combined-product writer, without changing v18
science. Its publication guarantees and filesystem requirements are explicit
in [the product schema reference](internal-schemas.md). Historical CI fixtures
now distinguish reproducible records from eligibility to execute a frozen
campaign on a different installed runtime; campaign admission remains exact.

The verified v15 cumulative terminal is a **scientific fail**: 1,115 binding
comparisons pass, 32 fail against the earlier Hebog incumbent and 40 are
underpowered. No binding comparison against either PyBDSF reference or Aegean
has a definite failure, but that does not establish general parity. All five
operational/product safety checks and 12 exact Serial/Dask comparisons pass.
The [campaign overview](phase-5-campaign-overview.md) contains the complete
non-passing endpoint and correctness inventory; exact evidence belongs in the
[execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md).
No earlier candidate's scientific pass transfers automatically to this one.
Terminal review confirmed two high-SNR corner-source cases where an invalid
free fit falls back to a beam-shaped model and publishes badly biased Gaussian
fluxes as measured. V16 repairs that admission defect: inadequate Gaussian
models are explicitly unavailable while independent source products remain.
V17 repairs excessive background/coarse-RMS edge extrapolation without changing
detection thresholds or flattening genuine affine gradients. Saved-plane
inspection identifies the nearly coincident fine-grid centres as the cause of
the large corner-background excursions; independent tests reproduce and fix
the conditioning defect. A bounded unchanged-pixel diagnostic also resolves
the historical displaced-Gaussian witness at the fitting boundary. Neither
closed campaign scores nor full notebook images were rerun for these claims.

Local public Serial/existing-Dask, frozen equivalence, notebook execution and
installed-wheel workflows pass. The wheel smoke reads and validates all four
products for blank, all-NaN, continuum, compact and custom-threshold controls.
This is a prepared **experimental standalone release candidate**, not final
release clearance. On **13 September 2026**, the human accepted deferring the
documented uncertainty-calibration, measurement-tail and faint-association
limitations for v17 within the standalone input envelope above. This closes
the bounded scientific risk-disposition gate, not the failed or inconclusive
campaign comparisons. Accumulated-branch merge review and the full platform
CI matrix remain required. The Rapthor acceptance lane still contains
seven expected-failure scaffolds, not passing deployment acceptance tests.
No further scientific run, publication or default cutover follows from this
handoff. Known correctness defects cannot be waived by an experimental label.

**Merge-review repair, 13 September:** a supported custom-threshold request
could fail against the private 75-sigma background-refinement trigger. On v17,
a synthetic 256-square noise image accepted detection/island thresholds of
100/74 but raised at 100/75 or 100/80; 100/80 succeeded at 81 square.
V18 reconciles that trigger with the caller's valid detection/island ordering,
including small bright-source inputs and the 150-pixel mesh transition.
The implementation (`ae96ee6...`) and its regression checks are recorded under
M4 in the plan; the new non-executable identity and live notebook guard are
verified. This closes that defect, not whole-branch or supported-platform CI
clearance.
Standard 5/3 science is unchanged, while provenance identifies the new
composition. No historical science verdict is revised.

## Release boundaries

| Delivery | Required before claiming it |
| --- | --- |
| Merge a small change | Coherent scope, review, applicable tests, current docs and CI. The custom-threshold repair is validated and frozen; whole-branch review and platform CI remain. The earlier campaign/severity disposition is preserved. |
| Experimental standalone `0.x` | Reviewed correctness inventory, tested installed public workflow, passing package/platform checks, explicit limitations and unqualified status. General parity, full Rapthor performance and facility scaling can follow in separate increments. |
| Scientifically qualified finder | Exact candidate-bound cumulative parity/retention, fresh held-out/public evidence and independent scientific/engineering acceptance. Frozen endpoints, margins and failed decisions remain unchanged. |
| Supported Rapthor deployment | Qualified science, profile/filter agreement, fallback, retry/resume, memory and matched complete `filter_skymodel` performance: at least 50% lower median than released PyBDSF and faster than pinned master, with the required confidence bounds. |
| Default cutover / `1.0` | Complete acceptance and facility-scale matrix, operational soak, production review and current supported-platform/documentation evidence. |

Release Please manages version changes, changelogs, tags and GitHub releases.
The maintainer reviews and merges its generated release PR after the intended
release scope passes its checks. The repository currently has no PyPI upload
workflow. An experimental release does not authorize another scientific
campaign, reinterpret closed evidence or change a workflow default.
