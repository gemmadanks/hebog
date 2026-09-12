# Use the notebooks and refresh comparisons

Run these commands from the repository root after `uv sync --all-groups`.
Marimo, plotting libraries and Hebog are included in that environment. No
individual notebook run needs to be frozen or reproduce a previous result.
Change parameters and explore; the finder remains experimental and its
[current limits](../reference/release-status.md) still apply.

## Choose a notebook

| Notebook | Purpose | Inputs and execution |
| --- | --- | --- |
| `source_finder_demo.py` | Start here: complete public `find_sources` workflow, catalogue, RMS, mask and diagnostics. | Generates a small synthetic shell locally and runs automatically. No downloads or saved campaigns. Products use a temporary session directory. |
| `astronomer_source_finder_workbench.py` | Explore images and detection thresholds through the public continuum API. | Two offline synthetic fields, three small LoTSS fields, or your FITS image. Press **Load selected image**, adjust parameters, then **Run Hebog continuum finder**. |
| `source_finder_internals.py` | Developer walkthrough of background, detection, measurement, tiling and multiscale stages. | Small synthetic inputs from checked-in recipes. Runs automatically. Uses internal APIs and temporary storage; it is not the recommended application integration example. |
| `campaign_source_finder_comparison.py` | Inspect saved finder results, source/component overlays, support diagnostics and Hebog implementation history. | Needs existing campaign inputs, result files and metadata. Opening it reads saved products; it does not run a finder. |

Open any of them with:

```console
uv run marimo edit notebooks/source_finder_demo.py
uv run marimo edit notebooks/astronomer_source_finder_workbench.py
uv run marimo edit notebooks/source_finder_internals.py
uv run marimo edit notebooks/campaign_source_finder_comparison.py
```

The offline demonstrations normally take seconds to a minute, depending on
compilation and machine load. Workbench time depends on the selected image;
the public API accepts at most 1,024 pixels along either spatial axis. The
comparison viewer can display larger existing diagnostic products, which is
not an extension of the public API's size limit.

## Download public inputs

Prefetch the three workbench LoTSS fields:

```console
uv run python scripts/benchmark/download_notebook_data.py
```

Files go to `benchmark-results/notebook-data/`, which the workbench reads
automatically. It also downloads a selected LoTSS field on demand if missing.
These three requests cover the 22-arcminute representative field,
12-arcminute 3C 295 field and 20-arcminute M51 field. They are small cutouts,
not whole surveys. The [LoTSS DR2 service](https://lofar-surveys.org/dr2_release.html)
controls the returned bytes; no historical checksum is enforced for these
exploratory inputs.

List optional inputs and advisory sizes before downloading larger files:

```console
uv run python scripts/benchmark/download_notebook_data.py --list
uv run python scripts/benchmark/download_notebook_data.py --dataset lotss-wide
uv run python scripts/benchmark/download_notebook_data.py --dataset hydra-deep-image --dataset hydra-shallow-image
uv run python scripts/benchmark/download_notebook_data.py --dataset sdc1-image
```

The optional SDC1 image alone is approximately 4 GiB, and the Hydra archive
approximately 9.3 GiB. They are never downloaded by default. The script also
lists the public beam, truth and submission files from the existing SDC1/Hydra
artifact inventory. Source URLs and historical sizes are reused from that
inventory; this downloader does not execute its old scientific authorization.

Downloads stream to disk. Existing non-empty files are reused, with basic
FITS checks for image files. `--overwrite` fetches a fresh copy and replaces
the old file only after a successful transfer. An interrupted transfer leaves
the previous file intact; rerun to restart the failed download. There is no
per-run checksum lock or experiment registry.

Use `--output-directory /path/to/images` for another location, then choose
**My FITS image** in the workbench. Its default input cache and output root
(`benchmark-results/notebook-runs/`) persist across sessions and stay outside
Git. You can change the output root in the UI. The basic demo and internals
notebook instead use temporary session directories.

A downloaded survey image is **not** a saved comparison campaign. The SDC1
campaign uses selected cutouts; LoTSS campaign images also have their own
normalization and metadata. Fresh downloads must not be substituted for those
files merely because the sky field looks the same.

## Prepare the comparison viewer

The default **Campaign root** is
`benchmark-results/phase-5/hebog-notebook-refreshes/latest`. You may instead
enter the directory of any supported saved public or synthetic campaign.

For the existing SDC1/Hydra/LoTSS refresh, these inputs must already be present:

- `benchmark-results/phase-5/current-public-plus-lotss-comparison/input-campaign/campaign.json`,
  with every referenced `inputs/<case>/input.json` and FITS image;
- `benchmark-results/phase-5/current-public-plus-lotss-comparison/reference-campaign/campaign.json`,
  with the saved released-PyBDSF and Aegean results and their native products;
- repository-relative files referenced by those records, including the public
  acquisition and selected-cutout directories; and
- for existing history, `benchmark-results/phase-5/hebog-notebook-refreshes/`
  with its `index.json`, run directories and referenced artifacts.

These generated files are ignored by Git. **There is currently no published
URL for the complete saved comparison bundle.** Restore it from the project's
existing data host or backup. In a fresh checkout, a complete restored
`benchmark-results/phase-5/` tree preserves the expected layout. For example:

```console
mkdir -p benchmark-results/phase-5
rsync -aL /path/to/saved/benchmark-results/phase-5/ benchmark-results/phase-5/
```

The `-L` copies symlink targets as files, so links to another machine's
scratch directories do not remain dangling. Keep all referenced products and
repository-relative paths together, not just `campaign.json` or the `latest`
symlink. Use the input/reference options below if restoring a different
supported campaign layout.

The downloader provides public raw data only. It does not download generated
Hebog/PyBDSF/Aegean results or rebuild the saved campaign. Rebuilding missing
reference results is a separate container-backed operation with its own
runtime and resource requirements; the historical one-look acquisition,
selection and campaign commands are not a clean-checkout bootstrap recipe.
The workbench can still be used immediately without those artifacts.

## Refresh Hebog results in the comparison notebook

First check the selected scientific implementation and available input records
without running a finder:

```console
uv run python scripts/benchmark/refresh_public_notebook_hebog.py --preflight-only
```

Then run a diagnostic refresh with a short label:

```console
uv run python scripts/benchmark/refresh_public_notebook_hebog.py --label "Current notebook comparison"
```

This runs current Hebog on the 13 saved SDC1/Hydra/LoTSS inputs and reuses the
26 saved released-PyBDSF/Aegean results. It does not execute either external
finder. Allow space for another set of Hebog products; elapsed time depends
on the full images and host and can be much longer than the small demo.

Completion registers the run under
`benchmark-results/phase-5/hebog-notebook-refreshes/`, updates `index.json`
and points `latest` to it. Reload the comparison notebook, select the desired
**Campaign root** and case, and choose runs in **Hebog implementation history**.
Unchanged identities reuse their existing completed results.

To continue an interrupted refresh:

```console
uv run python scripts/benchmark/refresh_public_notebook_hebog.py --resume --label "Current notebook comparison"
```

Resume requires the existing staging run's source, configuration, runner,
inputs and references. This guard protects saved comparison records; it does
not require ordinary workbench experiments to reproduce one another. After a
science change, run a new refresh rather than relabelling old results.

For an alternative saved input/reference set, paths must remain inside the
checkout and keep the same supported record layout:

```console
uv run python scripts/benchmark/refresh_public_notebook_hebog.py --input-campaign benchmark-results/my-inputs/campaign.json --reference-campaign benchmark-results/my-references/campaign.json --history-root benchmark-results/my-refreshes --preflight-only
```

Repeat with the same paths and `--label` instead of `--preflight-only` to run.
Enter that completed run directory in **Campaign root**; the notebook's
history selector still reads the default history index.

## Common problems

| Symptom | Action |
| --- | --- |
| No `campaign.json`, no cases, or missing FITS/native product | Restore the complete saved artifact tree or select another valid campaign root. Downloading raw survey images alone cannot fix missing comparison records. |
| `final public-interface identity changed` | The diagnostic runner's selected review does not match the science checkout. Current selection is the F4 filtered-response review, composition v15. A new scientific implementation needs its corresponding review and runner selection before this saved-comparison path can refresh. This is not a dependency-sync error; use the ordinary workbench for unrestricted exploration. |
| Existing staging directory | Resume an unchanged interrupted refresh with `--resume`; preserve older staging when its scientific identity differs. |
| LoTSS service unavailable or incomplete download | Retry the downloader. Use `--overwrite` to replace a bad cached file, or select an offline synthetic field. |
| Image exceeds 1,024 pixels in the workbench | Choose a smaller cutout. Larger campaign diagnostics do not imply public finder support for the same size. |

The refresh's preflight checks its current candidate and input records; it is
not a scientific qualification or a guarantee that every numerical fit will
succeed. Saved comparisons distinguish sources from Gaussian components and
retain explicit unavailable measurements. Finder agreement is diagnostic,
not ground truth, and these runs make no qualified performance claim.

## Check notebook execution

```console
just marimo-check
just notebook-smoke
```

The first command checks all four notebooks' structure. The second executes
the two offline demonstrations with a three-minute limit per notebook. CI
runs both checks. It checks successful execution only: there are no saved
plot snapshots, fixed catalogue counts or individual-run equality gates.
The interactive workbench actions and data-dependent campaign viewer still
need manual inspection when changed.

Keep HTML exports for inspection or sharing with:

```console
uv run python scripts/check_notebooks.py --output-directory benchmark-results/notebook-exports
```

For an individual notebook, Marimo also supports `export html`. A workbench
export with unpressed run buttons does not exercise an image analysis.
