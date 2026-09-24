# Hebog and other source finders

This page helps you decide whether Hebog suits your work, by comparing it with
the source finders most used for radio-continuum images. It describes methods
and software properties, not measured accuracy.

!!! warning "Hebog is experimental"
    The other tools here have produced published survey catalogues. Hebog has
    not, accepts images only up to 3,000 pixels per side today, and is not
    scientifically qualified. For a science catalogue now, use an established
    finder. See [capability and status](../reference/release-status.md).

## In one paragraph

Hebog is closest to **PyBDSF**: local background and RMS maps, two-threshold
islands, multi-Gaussian fitting, and à trous wavelets for extended emission.
It borrows Aegean's emphasis on reproducible, well-conditioned fits and
ProFound's idea of measuring extended flux from pixels rather than from
Gaussians. What is new is the software design: every step runs on independent
image tiles through a caller-supplied executor, so the same code runs in one
process or across a Dask cluster and must give the same answer. Among
established finders, only Selavy and CAESAR distribute one continuum image
over several nodes, and both do so with MPI.

## Methods at a glance

| Finder | Background and noise | Detection | Deblending and characterisation | Extended emission | Source flux |
| --- | --- | --- | --- | --- | --- |
| **Hebog** | Sigma-clipped grid, interpolated; source pixels protected; finer RMS grid near bright sources | Seed 5σ, grow to 3σ (user-set); beam-matched filters and B3 à trous scales add evidence | Peak and saddle splitting; bounded joint Gaussian fits with admission checks | Cross-scale wavelet hierarchy associates components into sources | Sum of fitted Gaussians, as PyBDSF; a signed non-overlapping aperture flux is published alongside |
| **PyBDSF** | Sliding box, sigma-clipped, interpolated; optional adaptive smaller box near bright sources | Islands at 3σ with a 5σ peak; optional false-detection-rate threshold | Multi-Gaussian fit per island; Gaussians grouped into S, C or M sources; optional shapelets | Optional à trous wavelet fit of the Gaussian residual | Sum of grouped Gaussians |
| **Aegean** | BANE: sliding-box sigma-clipped median and RMS, interpolated | Flood fill, seed 5σ, flood 4σ | Negative-curvature map sets component count; constrained Gaussian fit that accounts for correlated noise; priorized (forced) fitting | None; Gaussian-only | Per component |
| **Selavy** | Optional sliding-box noise; robust median and MADFM | Signal-to-noise cut with optional growth to a lower threshold | Gaussian fits per island, seeded by sub-thresholds or curvature | Optional à trous reconstruction before searching | Per island and per component |
| **CAESAR** | Local median and MAD boxes, interpolated | Flood fill, seed 5σ, merge 2.6σ; iterative | Nested blobs from multiscale curvature; optional Gaussian mixture fit | Saliency filter, wavelets, active contours or superpixel clustering | Per island and per component |
| **PySE** | SExtractor-style grid, sigma-clipped, interpolated | Detection and analysis thresholds (8σ and 3σ in the LOFAR Transients Pipeline); optional FDR | Multi-threshold deblending; one Gaussian per sub-island; forced fits at fixed positions | None | Per Gaussian |
| **ProFound** | Box-car sky and RMS grid with objects masked | Threshold on sky-subtracted image | Watershed segmentation, then segments dilate until flux converges; no Gaussians | Handled naturally by free-form segments | Sum of pixels in the segment |
| **SExtractor / SEP** | Mesh with clipped mode estimate, median filter, spline | 1.5σ over a minimum connected area after filtering | Multi-threshold tree; moments and aperture photometry | Limited | Aperture, Kron or isophotal |
| **BLOBCAT** | External RMS and background maps required | Flood fill, 5σ and 2.6σ | Parabola fit to each blob peak with bias corrections; no deblending | Blobs of any shape | Sum of blob pixels, corrected |

Thresholds are defaults or commonly used values; every tool lets you change
them. SExtractor was designed for optical images: its noise model assumes
uncorrelated pixels, and it does not deconvolve a radio beam or use the
Condon (1997) error formulae, so radio users normally supply an external RMS
map.

## Software and scalability

| Finder | Language and interface | Parallelism | Image must fit in memory | Outputs | Licence | Used by |
| --- | --- | --- | --- | --- | --- | --- |
| **Hebog** | Python library | Serial, threads, or a caller-owned Dask cluster; tiles with halos; Zarr intermediates | By design no; today limited to 3,000 px per side | FITS catalogue (islands, sources, Gaussians), RMS image, mask, JSON diagnostics with provenance | BSD-3-Clause | No survey yet; Rapthor integration planned |
| **PyBDSF** | Python with C++ and Fortran; API and interactive shell | Multiprocessing on one node | Yes | Gaussian and source lists in many formats; RMS, mean, model, residual and island images | GPL-3 | LoTSS, Rapthor, MIGHTEE, VLASS Quick Look |
| **Aegean** | Python; CLI and API | Multiple cores on one node; BANE can work in stripes | Yes | Component and island catalogues; residual and model images (AeRes) | AFL-3.0 | GLEAM, GLEAM-X, MWA transients |
| **Selavy** | C++; CLI with parameter files | MPI: sub-images with overlap, merged by a master process | No | Island and component catalogues; noise, threshold, residual and component images | Part of ASKAPsoft | RACS, EMU and other ASKAP surveys |
| **CAESAR** | C++; CLI with a config file | MPI and OpenMP tiles with edge-source merging | No | ROOT files, region files, ASCII catalogues, residual image | GPL-3 | ASKAP SCORPIO, EMU Galactic-plane studies |
| **PySE** | Python; CLI and API | One node | Yes | Source list with Condon-style errors | BSD-2-Clause | LOFAR Transients Pipeline, AARTFAAC |
| **ProFound** | R package | One node | Yes | Segmentation map and segment statistics | LGPL-3 | Optical surveys (GAMA, DEVILS); radio tests |
| **SExtractor / SEP / SourceXtractor++** | C with CLI / Python bindings / C++ | SourceXtractor++ is multithreaded and tile-based on one node | SourceXtractor++: no | Catalogues and check images | GPL-3 / LGPL / LGPL | Optical and infrared surveys |
| **BLOBCAT** | Python 2 script | None | Yes | Blob catalogue | — | ATLAS polarisation; unmaintained |

## How Hebog differs, tool by tool

### PyBDSF

PyBDSF is the reference Hebog is developed against, because Rapthor uses it.

- **Same family.** Both estimate background and RMS on a sigma-clipped grid,
  use a peak threshold and a lower island threshold, fit Gaussians, and use B3
  à trous wavelets for extended emission. Both can refine the RMS near bright
  sources.
- **Extended emission.** PyBDSF fits Gaussians to each wavelet scale of the
  residual and adds them to the source. Hebog uses the wavelet scales only as
  evidence for detection and association, and measures flux on the original
  pixels.
- **Source flux.** Both define a source's total flux as the sum of its
  Gaussians. Hebog additionally publishes a signed aperture flux measured on
  the original pixels, which retains diffuse emission no Gaussian fits and
  excludes sky outside the image. Compare Hebog's `GAUSSIAN_COMPONENTS` with
  PyBDSF's Gaussian list, and `SOURCES` with its source list.
- **Failures are explicit.** Hebog publishes a Gaussian only if the fit passes
  admission checks, and records every rejected or deferred item in
  `diagnostics.json`.
- **Fewer features.** Hebog has no shapelets, PSF-variation maps, spectral
  index or polarisation modules, no interactive shell, no false-detection-rate
  threshold, and does not publish model or residual images.
- **Scaling.** PyBDSF holds the whole image in memory and parallelises on one
  node. Hebog is built for tiles and clusters.
- **Code.** Hebog is an independent BSD-licensed implementation; it copies no
  PyBDSF code.

### Aegean

Aegean's curvature-based component finding and covariance-aware fitting are
known for low flux scatter on compact sources, and its priorized fitting is
the standard tool for light curves and multi-frequency catalogues. Hebog has
no forced-fitting mode and does not yet model pixel covariance in its default
fit. Aegean has no extended-emission treatment; Hebog's `continuum` profile
does. Hebog's development comparisons include Aegean as a second reference.

### Selavy and CAESAR

These are the two established finders that split one image across nodes.
Selavy divides the image into overlapping sub-images, and a master process
merges detections in the overlaps and re-measures them. CAESAR merges sources
at tile edges in a similar way.

Hebog differs in three ways. It uses Dask and a small executor protocol
instead of MPI, so it fits Python pipelines that already own a cluster. It
gives each pixel and each object exactly one owner, so nothing is measured
twice and merged afterwards. And it treats "the tiled result equals the
single-tile result" as a tested contract rather than an approximation. Both
Selavy and CAESAR are C++ applications configured by parameter files; neither
offers a Python API.

### ProFound

ProFound showed that free-form segments recover the flux of complex extended
sources better than sums of Gaussians (Hale et al. 2019). Hebog's
`ASSOCIATION_APERTURE_FLUX` follows the same reasoning, alongside the summed
Gaussian flux, beam deconvolution and position uncertainties that ProFound
does not provide.
ProFound is an R package.

### PySE

PySE targets fast, reliable measurement of compact and transient sources,
with forced fits at known positions. Hebog targets deep continuum images with
extended emission and has no forced-fitting or monitoring mode.

### Machine-learning finders

Detectors such as ClaRAN (Wu et al. 2019), DeepSource (Vafaei Sadr et al.
2019), ConvoSource (Lukic et al. 2019) and YOLO-CIANNA (Cornu et al. 2024)
work on image patches, scale well on GPUs, and have scored highly on the SKA
Science Data Challenge 1 simulations. They depend on a training set that
resembles the target survey and generally do not provide fitted shapes with
beam deconvolution or analytic uncertainties. Hebog is a classical finder:
it needs no training and its decisions are traceable, but it will not learn
survey-specific artefacts.

## What comparison studies have found

- **Hopkins et al. 2015** (ASKAP/EMU challenge, eleven finders). Differences
  between finders came mostly from background estimation and from deblending
  and characterisation, not from thresholding.
- **Hale et al. 2019.** PyBDSF, Aegean and ProFound all recover simulated
  Gaussian sources; ProFound traces complex morphology better, and
  Gaussian-based fluxes can be biased for extended sources.
- **Bonaldi et al. 2021** (SKA Science Data Challenge 1). Classical finders
  and neural networks both competed; team expertise mattered as much as the
  tool, and resolved, complex sources remained the open problem.
- **Boyce et al. 2023** (Hydra, five finders on ASKAP data and simulations).
  Aegean and PyBDSF had the best completeness; every finder handled a compact
  core embedded in diffuse emission poorly.

These findings shaped Hebog's priorities: robust source-protected noise
estimation, explicit handling of extended emission, and a pixel-based
aperture flux published next to the Gaussian sum.

## Which should I use?

| If you need… | Consider |
| --- | --- |
| A science catalogue today | PyBDSF or Aegean |
| Light curves or fixed-position fluxes | Aegean (priorized fitting) or PySE |
| Flux of complex extended sources, without Gaussians | ProFound |
| ASKAP-style distributed processing with MPI | Selavy or CAESAR |
| A finder embedded in a Python and Dask pipeline, with reproducible, provenance-tracked products, and you can accept experimental status | Hebog |

To run PyBDSF, Aegean and Hebog on the same images, see
[Use the notebooks](../how-to/notebooks.md).

## References

- Bertin & Arnouts 1996, A&AS 117, 393 (SExtractor).
  [doi:10.1051/aas:1996164](https://doi.org/10.1051/aas:1996164)
- Bonaldi et al. 2021, MNRAS 500, 3821 (SDC1).
  [doi:10.1093/mnras/staa3023](https://doi.org/10.1093/mnras/staa3023)
- Boyce et al. 2023, PASA 40, e027 and e028 (Hydra I and II).
  [doi:10.1017/pasa.2023.28](https://doi.org/10.1017/pasa.2023.28),
  [doi:10.1017/pasa.2023.29](https://doi.org/10.1017/pasa.2023.29)
- Carbone et al. 2018, Astron. Comput. 23, 92 (PySE).
  [arXiv:1802.09604](https://arxiv.org/abs/1802.09604)
- Condon 1997, PASP 109, 166 (errors on Gaussian fits).
  [doi:10.1086/133871](https://doi.org/10.1086/133871)
- Cornu et al. 2024, A&A 690, A211 (YOLO-CIANNA).
  [arXiv:2402.05925](https://arxiv.org/abs/2402.05925)
- Hale et al. 2019, MNRAS 487, 3971 (ProFound on radio images).
  [doi:10.1093/mnras/stz1462](https://doi.org/10.1093/mnras/stz1462)
- Hales et al. 2012, MNRAS 425, 979 (BLOBCAT).
  [doi:10.1111/j.1365-2966.2012.21373.x](https://doi.org/10.1111/j.1365-2966.2012.21373.x)
- Hancock et al. 2012, MNRAS 422, 1812, and 2018, PASA 35, e011 (Aegean).
  [doi:10.1111/j.1365-2966.2012.20768.x](https://doi.org/10.1111/j.1365-2966.2012.20768.x),
  [doi:10.1017/pasa.2018.3](https://doi.org/10.1017/pasa.2018.3)
- Hopkins et al. 2015, PASA 32, e037 (ASKAP/EMU challenge).
  [doi:10.1017/pasa.2015.37](https://doi.org/10.1017/pasa.2015.37)
- Lukic et al. 2019, Galaxies 7, 3 (ConvoSource).
  [doi:10.3390/galaxies7010003](https://doi.org/10.3390/galaxies7010003)
- Mohan & Rafferty 2015, ASCL 1502.007 (PyBDSF).
  [ascl.net/1502.007](https://ascl.net/1502.007),
  [documentation](https://pybdsf.readthedocs.io)
- Riggi et al. 2016, MNRAS 460, 1486, and 2019, PASA 36, e037 (CAESAR).
  [doi:10.1093/mnras/stw982](https://doi.org/10.1093/mnras/stw982),
  [doi:10.1017/pasa.2019.29](https://doi.org/10.1017/pasa.2019.29)
- Robotham et al. 2018, MNRAS 476, 3137 (ProFound).
  [doi:10.1093/mnras/sty440](https://doi.org/10.1093/mnras/sty440)
- Vafaei Sadr et al. 2019, MNRAS 484, 2793 (DeepSource).
  [doi:10.1093/mnras/stz131](https://doi.org/10.1093/mnras/stz131)
- Whiting & Humphreys 2012, PASA 29, 371 (Selavy).
  [doi:10.1071/AS12028](https://doi.org/10.1071/AS12028),
  [documentation](https://www.atnf.csiro.au/computing/software/askapsoft/sdp/docs/current/analysis/selavy.html)
- Wu et al. 2019, MNRAS 482, 1211 (ClaRAN).
  [doi:10.1093/mnras/sty2646](https://doi.org/10.1093/mnras/sty2646)
