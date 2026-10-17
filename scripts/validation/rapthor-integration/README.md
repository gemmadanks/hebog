# Rapthor's Hebog branch

Rapthor's native Hebog task is on a branch of
[Rapthor](https://git.astron.nl/RD/rapthor), not yet merged. The
[integration summary](integration-summary.json) records the tested commit,
based on Rapthor `main` at `aff260233a9a8c2ee19ce6616ea009402ecb86f0` and
tested with LSMTool `master` at `156ae6abd5cb89e7e622b9bd7a37ef7539a76ea2`,
the pins of 17 October 2026.
Rapthor declares `lsmtool>=1.9.0`; validation uses the pinned `master`.
Testing, trials and benchmarks use the branch; merging it matters only for
users of released Rapthor.

The branch adds `source_finder = hebog` to Rapthor's existing Prefect filter
task, using a caller-owned ThreadExecutor on its current one-single-threaded-
worker-per-node layout. It retains the PyBDSF subprocess for the default
backend and typed Hebog refusals, and adds dual-run reporting, memory
admission, blank/empty paths and retry reuse. It reserves the analysis memory
for the sources `hebog.expected_source_count` estimates from the detection
image, and falls back to PyBDSF when the worker cannot hold the analysis and a
tile task. Its `rapthor[hebog]` extra accepts any Hebog `0.x` release from
0.22, the first with that function and the first on PyPI; Hebog's feature
releases also bump the minor version, so a narrower range would block them.
The distributed executor and resource annotations are later work. No LSMTool
registry entry is needed.

The change is GPL-3.0 Rapthor code and stays in Rapthor's repository. It
contains no copied PyBDSF implementation. The small dummy-position record
adapts the two attributes LSMTool's existing dummy writer requires, preserving
that writer rather than duplicating its output format.

## Install and test

Install Rapthor at the summary's `rapthor_commit`, with Hebog from PyPI:

```bash
python -m pip install "rapthor[hebog] @ git+https://git.astron.nl/RD/rapthor.git@<rapthor_commit>"
```

The [container guide](../containers/rapthor/README.md) builds and tests
that commit. The branch's parset defaults, `hebog_profile = compact` and
`hebog_background = zero`, are the interim choice for Rapthor, which the
adapter also defaults to: of the four settings, they made LSMTool keep the
sky-model components pinned PyBDSF `master`'s mask keeps most often. They are
not scientifically qualified, and the matched benchmark measures the step's
performance.

## Frozen-field checkpoint

[The compact summary](integration-summary.json)
binds the four profile/background smoke checks to exact evidence records in
`benchmark-results/task20/profile-smoke/`. Every record is validated and
written by `hebog.validation.evidence`. All three frozen sources match and
pass the catalogue cuts in every setting; this is **not** the retained/rejected
component agreement matrix or a choice of profile/background. Input true/apparent
images are identical in this small frozen fixture.

The exact reproducer used, run from the Hebog checkout after `uv sync
--all-groups`, is below. It reuses valid bundles on retry and writes new dated
evidence; the generated FITS and full reports remain outside Git.

```bash
uv run python - <<'PY'
"""Frozen compact-field pin check; not profile qualification."""

import hashlib
import importlib.metadata
import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from astropy.table import Table

from hebog.adapters import (
    RapthorCompatibilityConfig,
    RapthorSourceFindingRequest,
    find_sector_sources,
)
from hebog.executors import SerialExecutor
from hebog.io import read_catalogue_fits_product
from hebog.validation.comparison import (
    compare_catalogues,
    compare_masks,
    compare_rms_maps,
)
from hebog.validation.evidence import (
    ScientificComparisonEvidence,
    SoftwareIdentity,
    write_evidence,
)
from hebog.validation.products import (
    canonical_product_set_sha256,
    load_fits_plane,
    load_mask_plane,
    load_pybdsf_catalogue,
    load_reference_product_manifest,
    product_set_by_reference,
    validate_reference_product_files,
)
from hebog.validation.quick_check import public_catalogue_sources

root = Path.cwd()
output = root / "benchmark-results/task20/profile-smoke"
output.mkdir(parents=True, exist_ok=True)
manifest = load_reference_product_manifest(
    root / "config/baselines/phase-0-pybdsf-reference-products.json"
)
validate_reference_product_files(root, manifest)
reference = product_set_by_reference(manifest, "master")
paths = {
    name: root / item.relative_path
    for name, item in reference.artifacts.items()
}
def sha(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()
inventory = json.dumps(
    sorted(
        (d.metadata["Name"], d.version)
        for d in importlib.metadata.distributions()
    )
).encode()
(output / "dependencies.json").write_bytes(inventory)
identity = SoftwareIdentity(
    name="hebog",
    version=importlib.metadata.version("hebog"),
    commit_sha=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip(),
    dependency_inventory_sha256=sha(inventory),
)
summary = []


def retained(table: Table) -> list[str]:
    return [
        str(row["Source_id"])
        for row in table
        if row["DC_Maj"] < 10 / 3600
        and row["E_RA"] < 2 / 3600
        and row["E_DEC"] < 2 / 3600
    ]


for profile in ("continuum", "compact"):
    for background in ("estimated", "zero"):
        name = f"{profile}-{background}"
        config = RapthorCompatibilityConfig(
            5, 3, profile=profile, background=background
        )
        config_bytes = json.dumps(asdict(config), sort_keys=True).encode()
        (output / f"{name}-config.json").write_bytes(config_bytes)
        image = (
            root / "tests/data/pybdsf/pybdsf-compact-reference-256/input.fits"
        )
        result = find_sector_sources(
            RapthorSourceFindingRequest(
                image, image, output / name / "sector", "task20-profile-smoke"
            ),
            config,
            SerialExecutor(),
        )
        cat = compare_catalogues(
            load_pybdsf_catalogue(paths["source_catalog.fits"]),
            public_catalogue_sources(
                read_catalogue_fits_product(
                    result.products_directory / "catalogue.fits"
                ),
                level="sources",
            ),
            beam_fwhm_degrees=4 / 3600,
            maximum_separation_beams=0.5,
            position_angle_minimum_axis_ratio=1.1,
        )
        products = {
            p.name: sha(p.read_bytes())
            for p in result.products_directory.iterdir()
            if p.is_file()
        }
        products_bytes = json.dumps(products, sort_keys=True).encode()
        (output / f"{name}-products.json").write_bytes(products_bytes)
        evidence = ScientificComparisonEvidence(
            schema_version=1,
            evidence_type="scientific-comparison",
            run_id="task20-" + name,
            captured_at=datetime.now(UTC),
            status="exploratory",
            dataset=manifest.dataset,
            candidate=identity,
            reference=reference.subject,
            candidate_product_manifest_sha256=sha(products_bytes),
            reference_product_manifest_sha256=canonical_product_set_sha256(
                reference
            ),
            configuration_sha256=sha(config_bytes),
            beam_fwhm_degrees=4 / 3600,
            maximum_separation_beams=0.5,
            catalogue=cat,
            true_sky_rms=compare_rms_maps(
                load_fits_plane(paths["true_sky_rms.fits"]),
                load_fits_plane(result.true_sky_rms_path),
            ),
            flat_noise_rms=compare_rms_maps(
                load_fits_plane(paths["flat_noise_rms.fits"]),
                load_fits_plane(result.flat_noise_rms_path),
            ),
            mask=compare_masks(
                load_mask_plane(paths["source_filter_mask.fits"]),
                load_mask_plane(result.mask_path),
            ),
        )
        write_evidence(output / f"{name}-evidence.json", evidence)
        summary.append(
            {
                "profile": profile,
                "background": background,
                "matched_sources": len(cat.matches),
                "candidate_sources": cat.candidate_count,
                "reference_sources": cat.reference_count,
                "candidate_catalogue_cut_retained": retained(
                    Table.read(result.source_catalog_path)
                ),
                "reference_catalogue_cut_retained": retained(
                    Table.read(paths["source_catalog.fits"])
                ),
                "evidence_sha256": sha(
                    (output / f"{name}-evidence.json").read_bytes()
                ),
            }
        )
(output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
PY
```
