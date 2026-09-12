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
approximately 9.3 GiB. The raw-data downloader does not fetch those by default.
The comparison setup below does fetch the SDC1 image. The downloader also
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

## Create a fresh PyBDSF/Aegean comparison

Use `prepare_notebook_comparison.py` to download the Hydra, LoTSS and SKA
SDC1 images and run both reference finders on the same 13 cases as the
existing comparison. It creates its own input and reference records;
no saved historical campaign is required. Hebog runs in a separate step.

Install Podman first. On macOS/Windows its Linux VM must already be running;
the script does not start, resize or restart a VM. Check the planned inputs
without downloading anything, building images or running containers:

```console
uv run python scripts/benchmark/prepare_notebook_comparison.py --build-images --dry-run
```

When disk space and compute resources are available, build the local reference
images and prepare the comparison:

```console
uv run python scripts/benchmark/prepare_notebook_comparison.py --build-images
```

The build downloads published PyBDSF 1.14.1 and AegeanTools 2.3.5 packages,
checks their hashes, and reuses the checked-in reference Containerfiles and
requirements. Only the released PyBDSF target is built; no historical master
wheel is needed. Container layers and build caches can require several GB in
addition to input images and native finder products. These are exploratory
runtimes: actual image IDs, dependencies and scientific options are recorded,
without requiring a historical campaign environment hash. The optional build
step requires network access. Finder execution disables container networking
and image pulling.

If the default images are already built, omit `--build-images`. To use other
local images containing those releases and their runtime dependencies:

```console
uv run python scripts/benchmark/prepare_notebook_comparison.py --pybdsf-image LOCAL_PYBDSF_IMAGE --aegean-image LOCAL_AEGEAN_IMAGE
```

The default selection preserves the previous comparison:

- **SKA SDC1:** eight 2,048-pixel cutouts from the Band 2 1,000-hour image,
  using the existing sparse, ordinary, crowded, resolved, close-pair,
  high-dynamic-range, low-apparent-SNR and primary-beam-boundary selections;
- **Hydra:** the published deep and shallow EMU pilot images;
- **LoTSS:** the 90-arcminute wide field, 3C 295 and M51.

The SDC1 cutouts retain their 75-pixel halos and core-only comparison products.
LoTSS inputs use the existing celestial-WCS and frequency normalization. The
script reads only the existing selection/settings, without launching a frozen
campaign. This creates fresh diagnostic results rather than reproducing the
old evidence hashes. It downloads six distinct images, including the roughly
4 GiB SDC1 image, and reuses that image for all eight cutouts. The Hydra archive,
SDC1 submissions, truth catalogue and primary-beam map are unnecessary for
these saved-product overlays and are not downloaded.

Runs are serial, with two cores per finder by default. Use repeated `--dataset`
options with case IDs listed by `--help` or `--dry-run` to select a subset;
for example, `--dataset hydra-deep --dataset lotss-dr2-m51-20arcmin`.
Use `--ncores` to set the CPU budget and `--output` to choose a new directory
inside the checkout. Raw downloads reuse the cache under
`benchmark-results/notebook-data/`; prepared cutouts remain with the comparison.

The default output is `benchmark-results/notebook-comparison/`:

- `input-campaign/` contains the input records, SDC1 cutouts and normalized
  LoTSS images needed by Hebog refresh; Hydra images use the shared cache;
- `reference-campaign/` contains both finders' native catalogues, masks or
  support proxies, normalized comparison catalogues, and notebook metadata;
- `request.json` records this setup's selected fields, runtimes and programs.

Open the comparison notebook and set **Campaign root** to
`benchmark-results/notebook-comparison/reference-campaign`. It is ready to
inspect both references before running Hebog. The PyBDSF operational settings
use 5-sigma detection and 3-sigma island thresholds with wavelets; Aegean uses
5-sigma seeds and 4-sigma flooding. These are the existing reference options,
not a threshold-matched completeness experiment. Aegean support is an explicit
proxy derived from its components, not a native detection mask.

To continue an interrupted setup, repeat the same options with `--resume` and
omit `--build-images`. Completed results are verified and reused; downloads
and unfinished finder work restart as needed. A failed setup does not publish
a completed reference campaign. Use a new output directory when changing
inputs, program versions or container identities. Existing results are never
overwritten, and no existing replay or campaign is resumed by this script.
If an image build failed before `request.json` was created, repeat the build
command without `--resume`.

### Add or refresh Hebog separately

For the fresh comparison, run:

```console
uv run python scripts/benchmark/refresh_public_notebook_hebog.py \
  --input-campaign benchmark-results/notebook-comparison/input-campaign/campaign.json \
  --reference-campaign benchmark-results/notebook-comparison/reference-campaign/campaign.json \
  --history-root benchmark-results/notebook-comparison/hebog-refreshes \
  --label "Current Hebog"
```

Add `--preflight-only` to check the selected Hebog candidate first. Repeat this
command after changing Hebog; add `--resume` only for an unchanged interrupted
refresh. It reuses the reference products and never runs PyBDSF or Aegean.
Set **Campaign root** to
`benchmark-results/notebook-comparison/hebog-refreshes/latest` to inspect all
three finders and the local Hebog history. Use a separate history directory
for each input/reference set so previously completed runs cannot be confused.
The existing Hebog candidate checks described below still apply.

## Open an existing saved comparison

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

To create a fresh comparison instead of restoring this historical bundle,
use the setup workflow above. It generates new reference products from public
images. The historical one-look acquisition, selection and campaign commands
are not needed for that workflow; they retain their original evidence scope.

## Refresh the existing SDC1/Hydra/LoTSS comparison

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
Enter that completed run directory in **Campaign root**. The history selector
reads its parent `index.json`; when viewing a reference campaign directly it
looks for a sibling `hebog-refreshes/` directory.

## Common problems

| Symptom | Action |
| --- | --- |
| No `campaign.json`, no cases, or missing FITS/native product | Complete the new setup or restore the complete saved artifact tree, then select its campaign root. Raw downloads alone do not contain comparison records. |
| Local image not found or wrong finder version | Use `--build-images` for a new setup, or supply compatible existing image tags. A build is never started implicitly. |
| Setup output already exists | Use `--resume` with unchanged options or choose a new `--output`. Omit `--build-images` when resuming. |
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

## Adding other source finders

Keep PyBDSF and Aegean as the initial comparison. SoFiA 2 primarily targets
3D spectral-line data cubes, especially H I surveys. A dedicated 2D experiment
could be useful, but should specify spatial smoothing, noise handling and
source measurement semantics rather than assume its cube workflow is a
like-for-like continuum comparison ([SoFiA 2 paper](https://arxiv.org/abs/2106.15789)).

For a next continuum comparison, consider ProFound first. Its segmentation
approach has been studied on compact and extended radio-continuum emission,
including flux recovery for complex sources
([radio ProFound study](https://arxiv.org/abs/1902.01440)). This is a recommendation
for a separate increment, not a new dependency or qualification requirement.
Each added finder needs native product interpretation, versioned settings,
empty/failure handling and a bounded diagnostic comparison before inclusion.
