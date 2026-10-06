# FAQ for astronomers

This FAQ explains how to evaluate Hebog and interpret its catalogues. It
connects the current public finder with lessons from the radio source-finding
literature. For a runnable example, start with
[Find sources in a FITS image](../tutorials/find-sources.md).

!!! warning "Experimental science"
    Hebog is not yet scientifically qualified for survey use or demonstrated
    to be interchangeable with PyBDSF. These answers describe the source
    checkout reviewed on **6 October 2026**, which may be ahead of an installed
    release. Consult [capability and status](../reference/release-status.md)
    for the current limits.

## Choosing and running Hebog

### What does a source finder actually identify?

A source finder identifies statistically significant emission in an image
and measures its position, brightness and shape under a chosen model. The
result depends on the noise estimate, detection rules and treatment of blends
and extended structure. Finding emission and identifying the galaxy that
produced it are separate tasks. Source-finding challenges assess both
detection and measurement accuracy.
[Hopkins et al. (2015)](https://doi.org/10.1017/pasa.2015.37)

Hebog estimates the background and local noise, detects emission, fits
Gaussians, and associates detections into image-domain sources. It does not
identify optical or infrared counterparts or classify physical objects.

### How does Hebog relate to PyBDSF and other finders?

Hebog is an independent implementation aimed first at the subset of PyBDSF
behaviour needed by Rapthor's `filter_skymodel` step. Its public library can
also run independently of Rapthor. Its design emphasises bounded image tiles
and execution through an existing Dask cluster; this design goal is separate
from demonstrated scientific accuracy or speed.

The literature offers several approaches worth distinguishing:

| Approach | Example and reading | Why it matters |
| --- | --- | --- |
| Gaussian decomposition and source grouping, with optional wavelet processing | [PyBDSF documentation](https://pybdsf.readthedocs.io/en/latest/) | A catalogue can contain several components for one source. |
| Compact-source fitting with correlated-noise treatment and priorized fitting | [Aegean 2.0, Hancock et al. (2018)](https://arxiv.org/abs/1801.05548) | Fitting at known positions answers a different question from blind detection. |
| Distributed radio source extraction | [Selavy, Whiting & Humphreys (2012)](https://doi.org/10.1071/AS12028) | Processing one image across nodes predates Hebog. |
| Flood-filled pixel measurements | [BLOBCAT, Hales et al. (2012)](https://arxiv.org/abs/1205.5313) | Thresholded pixel sums and fitted-model fluxes have different biases. |
| Segmentation and aperture growth | [ProFound radio tests, Hale et al. (2019)](https://doi.org/10.1093/mnras/stz1462) | Irregular extended emission need not be well represented by Gaussians. |

These papers do not rank Hebog: they predate it. A method's performance on one
test population is not a guarantee on another. See the broader
[source-finder comparison](source-finder-comparison.md) for method details.

### Can I use Hebog for a survey catalogue now?

Use it for bounded evaluation, demonstrations and integration development.
A successful run verifies that the software produced its expected products;
it does not establish completeness, reliability or calibrated uncertainties
for your survey. Current limitations include extended-source photometry and
centroids, crowded-field fitting and association, and beam sampling.

Both `development-unqualified` and `custom-unqualified` in the diagnostics
mean scientifically unqualified. The former identifies the development
example configuration, not an approved science mode. The
[scientific status](../reference/release-status.md#scientific-status) explains
the evidence and remaining limitations.

### Which images can I give it?

One primary-HDU FITS continuum image with:

- two spatial dimensions, with any extra axes of length one; a Stokes axis
  must select Stokes I;
- brightness in `Jy/beam`;
- ICRS or FK5 J2000 celestial coordinates;
- a restoring beam and a positive reference frequency;
- no more than 15,402 pixels on either side; if the shorter side is under
  600 pixels, no more than 1,000,000 pixels in total; and
- a restoring-beam major-axis FWHM no greater than 22 pixels.

Hebog accepts suitable headers from different telescopes; accepting a header
does not validate that telescope's images scientifically. Supply missing
unit, beam or frequency values through `SuppliedImageMetadata`. Supplied
values cannot override existing header values. Convert pixels as well as
metadata if changing units: labelling mJy/beam values as Jy/beam changes the
reported flux by a factor of 1,000.

The [input header contract](../reference/input-header-contract.md) lists
imager conventions and refusals. Cubes, Q/U/V and polarised-intensity images
are outside the current public interface.

### Does an accepted beam or mosaic guarantee valid measurements?

No. The 22-pixel limit is a computational bound, not a scientifically
validated sampling range. Hebog's noise windows are fixed in pixels; tests
with beams spanning 18–20 pixels have missed bright sources.

Hebog also uses one restoring beam, converted to pixel geometry at the image
centre. It does not read a spatially varying point-spread-function map or an
effective-frequency map. Header acceptance therefore cannot establish that
a wide mosaic has the right beam or frequency everywhere. These are
[known input limitations](../reference/input-header-contract.md#limitations);
check recovery across your field before interpreting its catalogue.

### Should I use a primary-beam-corrected image?

Choose the image according to the quantity you intend to measure, and record
that choice. Hebog measures the image supplied: it neither applies a
primary-beam correction nor accepts a separate detection image for measuring
flux on another image. A primary-beam-corrected image can meet the input
contract, but its spatially varying noise still needs inspection in the RMS
product. An apparent-sky image does not acquire corrected fluxes by passing
through Hebog.

The planned Rapthor workflow will distinguish true-sky and flat-noise
branches. That integration is not implemented; see
[integration status](../reference/release-status.md#integration-status).

### Do I need Dask, and is Hebog already faster than PyBDSF?

You can run with `SerialExecutor()` on one machine. Threads and a Dask client
you supply are other options; Hebog does not start a cluster. Dask workers
need shared access to the input and output locations. Executor choice is
intended to change where work runs, not the science.

No general speed advantage has been established. Small images may offer
little parallel work, and distributed execution adds overhead. The project
targets at least a 50% reduction in the complete Rapthor step's median wall
time against a pinned PyBDSF reference, but that deployment gate remains
unmet. Support for 100,000-by-100,000 images is a design target, beyond the
current accepted size. See [execution choices](../how-to/configure-a-run.md#use-several-cores-or-a-dask-cluster)
and the [performance evidence](../reference/performance-profile.md).

## Detection and noise

### What do 5σ, 3σ and seven pixels mean? Are they defaults?

They are the tutorial's explicit development settings. The public
`SourceFinderConfig` requires you to supply the detection threshold, lower
island threshold and minimum island size. Only the `continuum` profile and
absence of a maximum island size are defaults.

For the direct detection path, σ is the local RMS after background
subtraction: 5σ seeds a detection, 3σ grows its connected footprint, and the
pixel cut rejects regions that are too small. At a local RMS of
100 µJy/beam, those direct thresholds correspond to 0.5 and 0.3 mJy/beam
above the estimated background. Hebog also uses significance on filtered
scales, so not every detection needs an original pixel above 5σ.

Changing the pixel size changes what seven pixels means in beam areas.
Choose and evaluate settings for your data; the
[configuration guide](../how-to/configure-a-run.md) lists the controls.

### Does a 5σ threshold guarantee a reliable catalogue?

No. A threshold is a rule applied to an estimated noise field, not the
probability that a catalogue entry is astrophysical. Correlated noise,
imaging artefacts, a misestimated background and the number of places
searched affect false detections. Raising a threshold generally favours
reliability at the expense of faint-source recovery; its actual effect must
be measured on representative data. Source-finding tests show that noise
estimation and deblending matter alongside the threshold.
[Huynh et al. (2012)](https://doi.org/10.1071/AS11026)

Hebog does not expose a false-discovery-rate threshold or publish a
probability of reality for each row.

### Why does the RMS map vary, and can I supply my own?

Real images need not have uniform sensitivity. Hebog estimates background
and RMS on a clipped grid, protects source regions where possible, and in
the `continuum` profile refines local noise around bright sources. Nominal
coarse and fine windows span 150 and 35 pixels; small images use a reduced
coarse mesh or a constant estimate. Structure finer than those estimates is
not independently resolved.

In a sufficiently crowded field no clean fine window may remain, so Hebog
falls back to the coarse estimate, which can include source wings. Inspect
the RMS around bright sources, diffuse structure and image edges. An RMS
product marked `valid` does not certify every position's estimate.

The public request currently accepts neither an external RMS/background map
nor custom noise-grid sizes. See
[background and noise estimation](how-hebog-works.md#2-estimate-background-and-noise).

### How should I represent blank pixels? What does an empty catalogue mean?

Use NaN for missing floating-point pixels, or a valid FITS `BLANK` value for
integer data. Zeros are currently data, not an automatic mask. Constant or
zero-padded regions can produce zero or artificially small RMS estimates;
automatic handling of constant blocks remains
[planned work](https://github.com/gemmadanks/hebog/blob/main/plans/source-finder-implementation.md#path-to-100).

An empty catalogue can mean that nothing passed the chosen rules. First
check `result.rms.scientific_status`: `unavailable` means no usable positive
noise estimate existed. The resulting all-NaN RMS image, zero mask and empty
catalogue are not evidence of an empty sky. This can happen with noiseless
simulations or too few usable pixels. Check the input, RMS and diagnostics
before interpreting a non-detection.

### What is the difference between the continuum and compact profiles?

`continuum` is the default profile. It uses multiscale evidence to associate
components and measures source apertures alongside fitted Gaussian fluxes.
`compact` omits extended-source association and publishes one source per
admitted Gaussian, with no association-aperture flux.

The compact profile explicitly reports `extended-emission-incomplete`. It
does not provide an equivalent, cheaper catalogue for arbitrary continuum
emission. See [profile selection](../how-to/configure-a-run.md#choose-a-profile).

## Reading the catalogue

### Is a source the same as an island, a Gaussian or a galaxy?

No. Choose the population that answers your question:

| Table | Meaning | Typical use |
| --- | --- | --- |
| `ISLANDS` | Connected regions of the published detection mask | Inspect segmentation and detection footprints. |
| `GAUSSIAN_COMPONENTS` | Successfully admitted Gaussian fits with published parent sources | Compare component positions, fluxes and shapes with component catalogues. |
| `SOURCES` | Image-domain associations of detections | Study the grouped emission and its source-level measurements. |

An island may contain several sources; a source may span several islands or
contain several Gaussians. A continuum source can also have no Gaussian when
its aperture measurement succeeds but fitting does not. None of these rows
proves a physical association or identifies a host galaxy. See
[catalogue relationships](../reference/public-products.md#catalogue-populations-and-relationships).

### Which flux should I use, and why are there two source fluxes?

`PEAK_FLUX` is in Jy/beam; integrated fluxes are in Jy. Their numerical values
can be similar for an unresolved source, but they describe different
quantities. For an ideal Gaussian, its integrated flux is its peak multiplied
by the ratio of fitted Gaussian area to restoring-beam area.
[Condon (1997)](https://adsabs.harvard.edu/pdf/1997PASP..109..166C)

In the `continuum` source table:

- `INTEGRATED_FLUX` sums the admitted Gaussian components. These models
  integrate over the whole plane, including any model tails outside the
  image. If no Gaussian was admitted, a positive source-aperture measurement
  is used instead, with `aperture-flux-without-fitted-component`.
- `ASSOCIATION_APERTURE_FLUX` sums signed, background-subtracted pixels in
  the source's owned aperture and converts from Jy/beam to Jy using the beam
  area. A non-positive sum is left unavailable, not replaced with a sum of
  positive pixels only.

Use the fitted sum when comparing like Gaussian-model fluxes. Use the
aperture measurement when asking about observed emission inside that
footprint. Neither is automatically the true total flux: a fitted model can
miss diffuse structure, while an aperture can miss emission beyond its
boundary. Pixel-based measurements of complex radio emission are explored by
[Hale et al. (2019)](https://doi.org/10.1093/mnras/stz1462). Hebog's
[flux reference](../reference/public-products.md#what-the-two-source-fluxes-measure-and-where-they-part)
shows the distinction on injected examples.

### Will Hebog recover all diffuse or blended emission?

No. A source with high total flux can still have low surface brightness when
spread over many beams.
[Hopkins et al. (2015)](https://doi.org/10.1017/pasa.2015.37)

Hebog's beam-matched filters and à trous wavelet scales help detect and
associate extended structure; they do not guarantee its complete recovery.
Flux is measured on the original background-subtracted pixels or their
fitted models, not by summing wavelet coefficients.

Nearby peaks are deblended and neighbouring components can be fitted jointly.
A faint companion with no separate peak can be missed. A degenerate joint
fit can force other components into a beam-shaped fallback. Very large or
complex fitting problems can be deferred, leaving a detection without a
Gaussian measurement. Read the dispositions rather than treating every
missing component as a below-threshold source. The
[algorithm guide](how-hebog-works.md#4-deblend-and-fit-gaussians) and
[known limitations](../reference/release-status.md#scientific-status) describe
these cases.

### Are the quoted errors a complete uncertainty budget?

No. Available errors are one-sigma measurement estimates, not a complete
survey calibration or image-systematics budget. Radio image pixels can have
correlated noise, so treating every pixel as an independent measurement
misrepresents the information available to a fit.
[Condon (1997)](https://adsabs.harvard.edu/pdf/1997PASP..109..166C)
and [Hancock et al. (2018)](https://arxiv.org/abs/1801.05548)

Hebog's public Gaussian fits use diagonal weighting; do not assume they use
Aegean's covariance-aware fitting. The source error on a summed Gaussian flux
is the quadrature sum of available component errors, requiring all of them;
it does not propagate covariance between components. Calibration across all
morphologies and signal-to-noise ratios remains incomplete.

FITS NaN, or `None` through Hebog's readers, means unavailable, never zero.
Current continuum source rows leave position errors and deconvolved sizes
unavailable even when member Gaussians have them; compact-profile source rows
carry their component measurements. Check the
[field definitions and flags](../reference/public-products.md#fields-shared-by-sources-and-gaussian_components)
before selecting on an error or size.

### Are positions and sizes ready for cross-matching?

Positions are in ICRS degrees, including when the input is FK5 J2000. The
Gaussian-component RA error is an eastward angular uncertainty on the sky,
approximately the RA-coordinate uncertainty multiplied by cos(declination).
It is not an uncertainty in seconds of time or a raw RA-coordinate error.

A continuum source's position describes its emission footprint. It can fall
between lobes or inside a shell, so it need not coincide with a radio peak or
a host galaxy. Fitted sizes include the restoring beam; deconvolved sizes
attempt to remove it. `unresolved`, `major-axis-only` and unavailable shape
have different meanings. An absent minor axis is not a measured zero.
See [astrometry conventions](../reference/compact-astrometry.md) and the
[public output reference](../reference/public-products.md).

### Is the source mask a photometric aperture or a CLEAN mask?

It is a binary detection footprint: `1` marks retained publication support,
and connected regions define islands. It is not a source-label image, a
complete aperture, a model image or a prescribed CLEAN mask. Summing pixels
under it will not generally reproduce source `INTEGRATED_FLUX` or
`ASSOCIATION_APERTURE_FLUX`.

The public bundle contains the catalogue, RMS, mask and diagnostics. It does
not currently include background, model or residual images. See the
[mask reference](../reference/public-products.md#source-filtering-mask-fits-image).

### Why can a visible detection have no catalogue row?

Detection, fit acceptance and publication are separate decisions. A rejected
or deferred fit has no Gaussian row; an admitted fit also needs a published
parent source. A continuum source without an admitted fit needs a usable
position and positive signed aperture flux to publish a row.

Read `diagnostics.json` → `measurement_dispositions` for the component or
source, including `catalogue_row_published` and its measurement outcome.
The diagnostics retain identities absent from the tables. The
[diagnostics reference](../reference/public-products.md#diagnostics-json)
explains the records.

## Evaluating and reporting results

### What are completeness and reliability, and how should I measure them?

For a specified population and matching rule, **completeness** is the fraction
of true sources recovered; **reliability** is the fraction of reported
detections that correspond to true sources. They answer different questions.
Source-finding challenges measure them alongside position and flux errors,
including separate tests of compact and extended emission.
[Hopkins et al. (2015)](https://doi.org/10.1017/pasa.2015.37)

For a Hebog evaluation, inject known sources spanning flux, size, morphology,
crowding and edge distance into representative noise, and reserve independent
cases for evaluation. Measure recovery and flux/position residuals by those
properties. Use realistic beam-correlated noise as well as simple analytic
tests. Image-plane injections test the finder on that image; they do not
measure emission lost during interferometric imaging.

A deeper catalogue helps, but unmatched rows are not automatically false:
the reference has its own selection effects and resolution. The
[Hydra II study, Boyce et al. (2023)](https://doi.org/10.1017/pasa.2023.29)
illustrates evaluating several finders using simulated and real radio images.

### Why does Hebog disagree with PyBDSF, even at the same thresholds?

Matching threshold numbers does not match the noise maps, deblending,
admission of fits, source associations or photometric estimators. Compare
Hebog `GAUSSIAN_COMPONENTS` with Gaussian/component lists, and `SOURCES` with
source lists. Match coordinate frames, units, beam, input image and science
settings before attributing a difference to accuracy.

Examine missed and additional detections, one-to-many associations, flux and
position residuals, and uncertainty coverage. Two catalogues can have the
same row count while containing different objects. Neither PyBDSF agreement
nor a larger catalogue alone establishes truth. The SKA challenge shows why
detection and characterisation must both be evaluated across source types.
[Bonaldi et al. (2021)](https://doi.org/10.1093/mnras/staa3023)

Hebog's [comparison notebook guide](../how-to/notebooks.md) and
[evaluation checklist](../reference/public-products.md#evaluation-checklist-for-astronomers)
describe the available development workflow.

### Can I measure spectral indices, polarisation or light curves?

The current public finder analyses one Stokes-I plane at one reference
frequency. It does not fit spectra, analyse polarisation, perform forced
photometry, or associate sources across epochs. `REFERENCE_FREQUENCY` is
metadata, not a spectral-index measurement.

For context, Aegean's priorized fitting can hold source position and shape
fixed while fitting flux in new data; it is designed for questions that blind
thresholding alone cannot answer.
[Hancock et al. (2018)](https://arxiv.org/abs/1801.05548)
Do not interpret a missing Hebog row in another epoch as zero flux.

### What should I keep with a result or report in a paper?

Keep all four output files, the returned result record, the exact Hebog
version or commit, the environment, the input identity, supplied metadata,
profile and thresholds. Diagnostics record checksums of the input,
configuration, science profile and implementation. Record which catalogue
population and flux estimator your analysis used, plus your selection and
matching rules and the evidence for completeness and uncertainty calibration.

Pin the version: Hebog's experimental `0.x` releases do not promise API or
schema compatibility. Save new runs in new output directories; existing
ones are refused. Software provenance makes a result reproducible, while
validation on appropriate data establishes what it can support
scientifically. See [provenance](../reference/public-products.md#provenance).

## Further reading

The links beside each answer identify its scientific sources. Useful starting
points are the [ASKAP/EMU challenge](https://doi.org/10.1017/pasa.2015.37) for
evaluation, [Aegean 2.0](https://arxiv.org/abs/1801.05548) for correlated-noise
and priorized fitting, [the ProFound radio study](https://doi.org/10.1093/mnras/stz1462)
for complex emission, and [Condon (1997)](https://adsabs.harvard.edu/pdf/1997PASP..109..166C)
for Gaussian-fit uncertainties. The
[comparison page's bibliography](source-finder-comparison.md#references)
provides a longer reading list.
