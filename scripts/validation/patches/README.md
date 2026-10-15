# Native Hebog task for Rapthor

Task 20 prepares this upstream patch for human publication. It targets Rapthor
`main` at `d0e7e148aa127838e9d4c91472c88ab992b4f29f`, the pin plan task 23's
checkpoint moved to on 13 October 2026, when ASTRON's authoritative `main`
and LSMTool `master` pointed to it and to
`9bac2f7fabdc15cd9490acfeb9c292aa72af59b7`. The one commit since the earlier
pin, `c6196cb4`, changes calibration and imaging BDA defaults; the contract
audit found nothing that touches the filter step. Rapthor declares `lsmtool>=1.9.0`;
validation uses the latest pinned `master`, as the plan requires.

The patch adds `source_finder = hebog` to Rapthor's existing Prefect filter
task, using a caller-owned ThreadExecutor on its current one-single-threaded-
worker-per-node layout. It retains the PyBDSF subprocess for the default
backend and typed Hebog refusals, and adds dual-run reporting, memory
admission, blank/empty paths and retry reuse. It reserves the analysis
memory for the sources `hebog.expected_source_count` estimates from the
detection image, and falls back to PyBDSF when the worker cannot hold the
analysis and a tile task (plan task 77). Its `rapthor[hebog]` extra needs
Hebog 0.22, the first release with that function. The maintainer scoped the work
to this layout on 12 October; task 72 owns the distributed executor and
resource annotations. No LSMTool registry entry is needed.

The patch modifies GPL-3.0 Rapthor and remains under Rapthor's licence. It
contains no copied PyBDSF implementation. The small dummy-position record
adapts the two attributes LSMTool's existing dummy writer requires, preserving
that writer rather than duplicating its output format.

## Apply and test

Use a clean Rapthor checkout or a new worktree. Do not apply over unrelated work:

```bash
git switch --no-track -c feat/hebog-native-task d0e7e148aa127838e9d4c91472c88ab992b4f29f
git am /path/to/hebog/scripts/validation/patches/rapthor-native-hebog.patch
```

A replayed commit can have a different committer/hash. Record its actual
identity when archiving it for the [container](../containers/rapthor/README.md).
The versioned integration summary records the originally tested commit and
tree. The patch is prepared locally; upstream publication and merge remain
human actions. Its parset defaults, `hebog_profile = compact` and
`hebog_background = zero`, are task 21's interim choice for Rapthor, which
the adapter also defaults to: of the four settings, they made LSMTool keep
the sky-model components pinned PyBDSF `master`'s mask keeps most often.
They are not scientifically qualified, and task 23 owns matched
complete-step performance.

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
"""Task-20 frozen compact-field pin check; not task-21 profile qualification."""

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
