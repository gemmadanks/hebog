# Phase 0 baseline results

Phase 0 has matched reviewed performance evidence for released PyBDSF 1.14.1
and PyBDSF master at
`c70103be3ae9ae9908286f144e6ce956acc0ce5c`. Every campaign uses one warm-up
followed by five measurements in a fresh container per repetition.

## Observed matched medians

| Dataset and metric | PyBDSF 1.14.1 | PyBDSF master | Master change |
| --- | ---: | ---: | ---: |
| Compact 256 complete | 0.715 s | 0.672 s | 6.1% faster |
| Representative 3,000 complete | 46.654 s | 45.015 s | 3.5% faster |
| Representative true-sky PyBDSF stage | 32.945 s | 31.860 s | 3.3% faster |
| Representative flat-noise PyBDSF stage | 12.851 s | 12.694 s | 1.2% faster |
| Representative complete CPU | 127.915 s | 125.352 s | 2.0% lower |

Maximum measured representative RSS was 1,302,822,912 bytes for release and
1,303,146,496 bytes for master. RSS is the maximum of parent sampling and
`RUSAGE_SELF`/`RUSAGE_CHILDREN`; it is not aggregate concurrent-child memory.
PyBDSF does not expose array-copy counters, so count and bytes are `null` with
an explicit reason. These external single-process runs use no Dask executor;
task, transfer, and spill counts are applicable zeroes.

The representative medians replace the earlier single Rapthor observation.
They establish comparison anchors, not evidence that Hebog has met its future
speed gates.

## Scientific reference products

The compact campaigns emit all seven standardized Rapthor-facing products.
The released and master catalogues contain the same three sources with exact
coordinate and flux agreement; true-sky RMS, flat-noise RMS, and mask arrays
also agree exactly. Catalogue file bytes differ because they identify the
generating PyBDSF version.

`config/baselines/phase-0-pybdsf-reference-products.json` binds each checked-in
artifact to its source run and complete provenance. The independent report is
`config/baselines/phase-0-pybdsf-master-vs-release-comparison.json`. It is
labelled exploratory because released-versus-master agreement is reference
characterisation, not independent scientific truth. Run
`just test-equivalence` to validate checksums and recompute the catalogue, RMS,
and mask reports.

## Warm one-tile overhead

The local exploratory probe used the compact 256-square input, one warm-up,
and 50 measurements. All provisional 95th-percentile budgets passed:

| Operation | Median | 95th percentile | Budget |
| --- | ---: | ---: | ---: |
| Configuration construction | 0.0008 ms | 0.0010 ms | 250 ms |
| FITS open and complete plane read | 2.778 ms | 4.071 ms | 500 ms |
| One-core/clipped-halo planning arithmetic | 0.0010 ms | 0.0011 ms | 10 ms |
| Serial one-batch dispatch | 0.0004 ms | 0.0005 ms | 5 ms |
| Reused one-worker thread-pool dispatch | 0.0175 ms | 0.0502 ms | 50 ms |
| Caller-owned warm Dask one-batch dispatch | 11.393 ms | 14.548 ms | 500 ms |

The planning and local-thread results measure the Phase 0 framework proxies,
not production implementations. Phase 1 must replace them with the real
partition planner and local executor without relaxing the budgets. Dask client
startup is deliberately excluded because Hebog accepts a caller-owned client.
The complete environment-bound record is
`config/baselines/phase-0-one-tile-overhead.json`.

## Reproduction workflow

Set `RAPTHOR_CHECKOUT` and `PYBDSF_CHECKOUT` to the recorded local checkouts.
Every output directory below must not already exist.

Materialize the compact governed input:

```console
uv run python scripts/validation/materialize_dataset.py \
  config/datasets/phase-0-regression.json \
  pybdsf-compact-reference-256 \
  benchmark-results/phase-0/input/reference-256.fits
```

Build the pinned master wheel in the immutable reference image:

```console
uv run python scripts/benchmark/build_pybdsf_master_wheel.py \
  --pybdsf-repo "$PYBDSF_CHECKOUT" \
  --container-image localhost/rapthor-dev:ci-aligned \
  --expected-container-digest \
  sha256:dce93991e2e671428ff8043a7e0d132294d2d2decf1e1587e9904d3e8f49b754 \
  --output-directory benchmark-results/wheels/rebuilt-master \
  --expected-sha256 \
  2f1fdfbecd39de93bad53e2a85258959e5114e1f049787ac15c763e8fc8f4d8d
```

Run the released compact campaign:

```console
uv run python scripts/benchmark/run_phase0_pybdsf_baseline.py \
  --container-image localhost/rapthor-dev:ci-aligned \
  --reference release \
  --rapthor-repo "$RAPTHOR_CHECKOUT" \
  --flat-noise-image benchmark-results/phase-0/input/reference-256.fits \
  --true-sky-image benchmark-results/phase-0/input/reference-256.fits \
  --dataset-id pybdsf-compact-reference-256 \
  --output-directory benchmark-results/phase-0/rebuilt-compact-release \
  --warmups 1 --repetitions 5 --ncores 4
```

Run master with the same arguments, changing `--reference`, adding
`--master-wheel` with the emitted wheel path, and selecting a new output
directory. For the representative campaign, use the environment-neutral
identifiers and checksums in
`config/baselines/phase-0-representative-dataset.json` to resolve the two
images, two sky models, vertices, and Measurement Set, then supply the
corresponding optional runner arguments.

After each campaign:

1. Compile its raw records with
   `scripts/benchmark/compile_phase0_pybdsf_evidence.py`.
2. Freeze compact products with
   `scripts/validation/freeze_reference_products.py`.
3. Persist the reference divergence report with
   `scripts/validation/compare_reference_products.py`.
4. Run `just test-equivalence` and load every evidence document through its
   typed loader.

Raw campaigns stay under ignored `benchmark-results/`; only compact products,
validated evidence, and environment-neutral reproduction metadata enter Git.
