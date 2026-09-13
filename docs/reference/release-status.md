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
| Thresholds | The 5/3-sigma, seven-pixel reference configuration reports `development-unqualified`. Other valid caller settings execute and report `custom-unqualified`. |
| Invalid/empty measurements | Invalid pixels are excluded. Unavailable noise, fits or uncertainties remain explicit; a noiseless emission image with unavailable RMS is not evidence of an empty sky. |
| Products | Source, Gaussian-component and island populations are distinct. Catalogue JSON/FITS and diagnostics schemas are versions 3/4/8; stale schemas fail clearly. |
| Workflow | One scientific image per request. Full Rapthor true-sky/flat-noise filtering integration, operational qualification and complete-path speed evidence remain work to do. |
| Scale | Bounded stages and Dask foundations exist. The complete public finder has not established 100,000-square or hundreds-of-node support. |

Start with [Find sources](../tutorials/find-sources.md). Do not infer public
large-image support from internal-stage tests or use associated-source rows
as if they were Gaussian-component measurements.

## Evidence and unresolved limitations

The development composition is v16, with a narrow Gaussian-fallback repair
under validation. The latest completed campaign is v15 (`73ab5af...`). Focused
repair tests, frozen small equivalence checks, portable coverage and exact
Serial/existing-Dask checks pass. The bounded public screen completed but
retains 49 point-estimate warnings, including compact uncertainty/measurement
and faint extended association, mask and flux-tail risks. It does not provide
powered parity evidence.

The verified v15 cumulative terminal is a **scientific fail**: 1,115 binding
comparisons pass, 32 fail against the earlier Hebog incumbent and 40 are
underpowered. No binding comparison against either PyBDSF reference or Aegean
has a definite failure, but that does not establish general parity. All five
operational/product safety checks and 12 exact Serial/Dask comparisons pass.
The [campaign overview](phase-5-campaign-overview.md) contains the complete
non-passing endpoint and correctness inventory; exact evidence belongs in the
[execution log](https://github.com/gemmadanks/hebog/blob/main/LOG.md).
No earlier candidate's scientific pass transfers automatically to this one.
Terminal review confirms two high-SNR corner-source cases where an invalid
free fit falls back to a beam-shaped model and publishes badly biased Gaussian
fluxes as measured. This is a release correctness blocker, not an experimental
limitation waived by passing aggregate metrics. A narrow independently tested
fallback-admission repair is implemented in v16 using independent controls;
it is not a general parity or release clearance. Inspection also confirms
large corner-background errors in the saved missing-source cases, with
ill-conditioned mesh-boundary extrapolation a concrete cause hypothesis.
This separate background problem remains a correctness blocker. The earlier
notebook position witness also needs resolution confirmation; statistical uncertainty and
ambiguous faint morphology need explicit reviewed limitations. No further
scientific run or release is authorized by documenting this result.

## Release boundaries

| Delivery | Required before claiming it |
| --- | --- |
| Merge a small change | Coherent scope, review, applicable tests, current docs and CI. The accumulated finder branch also needs its pending campaign/severity review. |
| Experimental standalone `0.x` | Reviewed correctness inventory, tested installed public workflow, passing package/platform checks, explicit limitations and unqualified status. General parity, full Rapthor performance and facility scaling can follow in separate increments. |
| Scientifically qualified finder | Exact candidate-bound cumulative parity/retention, fresh held-out/public evidence and independent scientific/engineering acceptance. Frozen endpoints, margins and failed decisions remain unchanged. |
| Supported Rapthor deployment | Qualified science, profile/filter agreement, fallback, retry/resume, memory and matched complete `filter_skymodel` performance: at least 50% lower median than released PyBDSF and faster than pinned master, with the required confidence bounds. |
| Default cutover / `1.0` | Complete acceptance and facility-scale matrix, operational soak, production review and current supported-platform/documentation evidence. |

Release Please manages version changes, changelogs, tags and GitHub releases.
The maintainer reviews and merges its generated release PR after the intended
release scope passes its checks. The repository currently has no PyPI upload
workflow. An experimental release does not authorize another scientific
campaign, reinterpret closed evidence or change a workflow default.
