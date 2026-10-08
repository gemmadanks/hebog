# FAQ for astronomers

Most questions about running Hebog and reading its products are answered on
other pages, linked in the first section. The rest of this page answers what
those pages do not: what the input and settings cannot do, and how to judge
what a catalogue supports, with pointers to the source-finding literature.

## Answered elsewhere

| Question | Answer |
| --- | --- |
| Can I use Hebog for a survey catalogue now? | [Scientific status](../reference/release-status.md#scientific-status) |
| Which images can I give it, and what can I supply when the header lacks a value? | [Supported inputs](../reference/release-status.md#supported-inputs-and-behaviour) and [what the finder reads](../reference/input-header-contract.md#what-the-finder-reads) |
| Does an accepted beam or mosaic guarantee valid measurements? | [Input limitations](../reference/input-header-contract.md#limitations) |
| How should I mark blank or zero-padded pixels? | [Invalid pixels](../reference/input-header-contract.md#invalid-pixels) |
| What do the detection and island thresholds mean? | [Set detection thresholds](../how-to/configure-a-run.md#set-detection-thresholds) |
| Should I use the `continuum` or the `compact` profile? | [Choose a profile](../how-to/configure-a-run.md#choose-a-profile) |
| Do I need Dask? | [Use several cores or a Dask cluster](../how-to/configure-a-run.md#use-several-cores-or-a-dask-cluster) |
| Is Hebog faster than PyBDSF? | [Performance](../reference/progress-against-goals.md#performance) |
| How does Hebog differ from PyBDSF, Aegean and other finders? | [Hebog and other source finders](source-finder-comparison.md) |
| How are the background and RMS estimated, and why does the RMS vary? | [Estimate background and noise](how-hebog-works.md#2-estimate-background-and-noise) and [the RMS image](../reference/public-products.md#rms-fits-image) |
| What does an empty catalogue mean? | [If the catalogue is empty](../tutorials/find-sources.md#if-the-catalogue-is-empty) |
| Will Hebog separate blends and recover diffuse emission? | [Deblend and fit Gaussians](how-hebog-works.md#4-deblend-and-fit-gaussians) and the [known limitations](../reference/release-status.md#scientific-status) |
| Is a source the same as an island, a Gaussian or a galaxy? | [Three populations, not one](how-hebog-works.md#three-populations-not-one) and [catalogue relationships](../reference/public-products.md#catalogue-populations-and-relationships) |
| Which source flux should I use? | [What the two source fluxes measure](../reference/public-products.md#what-the-two-source-fluxes-measure-and-where-they-part) |
| Where does a source's position lie, and when does it have a shape? | [Source fields](../reference/public-products.md#source-only-fields-and-measurement-meaning) and [beam deconvolution](../reference/compact-astrometry.md#beam-deconvolution) |
| How are the errors computed, and do they allow for correlated noise? Is the RA error in seconds of time? | [Point estimator and covariance](../reference/compact-fitting.md#point-estimator-and-covariance) and [uncertainty status](../reference/compact-astrometry.md#uncertainty-status) |
| Is the source mask a photometric aperture or a CLEAN mask? | [The source mask](../reference/public-products.md#source-filtering-mask-fits-image) |
| Why does a detection have no catalogue row? | [Measurement dispositions](../reference/public-products.md#measurement-dispositions) |
| Are background, model or residual images published? | [Publish products](how-hebog-works.md#6-publish-products) |
| What should I check before using a result as evidence? | [Evaluation checklist](../reference/public-products.md#evaluation-checklist-for-astronomers) |
| How do I re-run or reproduce a result? | [Re-run or retry](../how-to/configure-a-run.md#re-run-or-retry) and [provenance](../reference/public-products.md#provenance) |
| How do I run PyBDSF and Aegean on the same images? | [Use the notebooks](../how-to/notebooks.md) |

## The input and the settings

### Should I use a primary-beam-corrected image?

Choose the image for the quantity you want to measure, and record the
choice. Hebog measures the one image it is given: it applies no primary-beam
correction and cannot detect on one image while measuring on another, so
fluxes from an apparent-sky image stay apparent. A primary-beam-corrected
image is accepted, but its noise rises towards the edge of the beam; check
the RMS image there. Hebog does not
[combine](../reference/release-status.md#integration-status) a corrected
image with a flat-noise one.

### Are 5σ, 3σ and seven pixels defaults?

No. `SourceFinderConfig` has no default detection threshold, island
threshold or minimum island size; the tutorial's values are an example, not
a recommendation. Only the profile (`continuum`) and the absent maximum
island size have defaults. The minimum island size counts pixels, so what it
means in beams depends on how finely the image samples the beam: a beam
covers 1.13 FWHM² pixels, so seven pixels is about a quarter of a beam whose
FWHM spans five. Choose the settings for your data and measure their
effect.

### Can I supply my own RMS or background map?

No. The request takes no external RMS or background image, and the profile
fixes the noise grids. You can compare the RMS image Hebog publishes with
your own.

## Judging the catalogue

### Does a 5σ threshold guarantee a reliable catalogue?

No. A threshold is a rule applied to an estimated noise field, not the
probability that an entry is real. Correlated noise, imaging artefacts, a
misestimated background and the number of independent beams searched all
add false detections, and raising the threshold trades faint-source recovery
for reliability by an amount you have to measure on representative data.
In a challenge of eleven finders, the noise estimate and deblending changed
catalogues more than the threshold did
([Hopkins et al. 2015](https://doi.org/10.1017/pasa.2015.37));
[Huynh et al. (2012)](https://doi.org/10.1071/AS11026) compare fixed and
false-discovery-rate thresholds by completeness and reliability. Hebog has
no false-discovery-rate threshold and gives no per-row probability that a
detection is real.

### What are completeness and reliability, and how should I measure them?

For a stated population and matching rule, completeness is the fraction of
true sources recovered and reliability the fraction of reported detections
that are true sources. Source-finding challenges measure both, together with
position and flux errors, for compact and extended emission separately
([Hopkins et al. 2015](https://doi.org/10.1017/pasa.2015.37)).

To measure them for Hebog, inject sources spanning flux, size, morphology,
crowding and distance from the edge into representative noise, including
beam-correlated noise, and keep independent cases for the final evaluation.
Report recovery and residuals as functions of those properties. Image-plane
injections test the finder on that image; they do not measure emission lost
in imaging. A deeper catalogue helps, but a row it lacks is not necessarily
false, because the reference has its own selection and resolution
([Boyce et al. 2023](https://doi.org/10.1017/pasa.2023.29) evaluate several
finders this way on simulated and real images).

### Why does Hebog disagree with PyBDSF at the same thresholds?

Equal threshold numbers do not make equal noise maps, deblending, fit
admission, source grouping or photometry, so the catalogues differ even on
one image. Before attributing a difference to accuracy, match the input
image, frame, units and beam, and compare like populations, as the
[evaluation checklist](../reference/public-products.md#evaluation-checklist-for-astronomers)
describes. Look at missed and extra detections, one-to-many matches and the
flux and position residuals, not only the row counts: two catalogues can
have the same number of rows and different objects. Agreement with PyBDSF
does not establish truth, and neither does a longer catalogue; the SKA
Science Data Challenge 1 showed that detection and characterisation must
both be judged across source types
([Bonaldi et al. 2021](https://doi.org/10.1093/mnras/staa3023)).

### Do the errors include everything?

No. The published errors are the statistical errors of each fit. They do not
include the flux-scale calibration, primary-beam or imaging systematics, or
the uncertainty of the background and noise estimates, and their own
calibration across morphologies and signal-to-noise ratios is
[not yet complete](../reference/release-status.md#scientific-status). Add
the systematic terms your analysis needs.

## Beyond one image

### Can I measure spectral indices, polarisation or light curves?

Not with Hebog alone. It analyses one Stokes I plane at one reference
frequency and has no forced photometry or association across epochs or
frequencies. A source missing from a run on another epoch or band is not a
measurement of zero flux: to measure flux at known positions, use a finder
with forced fitting, such as Aegean's priorized fitting
([Hancock et al. 2018](https://doi.org/10.1017/pasa.2018.3)); see
[which finder to use](source-finder-comparison.md#which-should-i-use).

### What should I report in a paper?

Keep the exact Hebog version, the four products and the returned result
record; the diagnostics'
[provenance](../reference/public-products.md#provenance) identifies the
input, configuration, science profile, implementation and any supplied
metadata. State which population (`SOURCES` or `GAUSSIAN_COMPONENTS`) and
which flux you used, your selection and matching rules, and the evidence for
completeness, reliability and the errors. Releases make no
[compatibility promise](../reference/release-status.md#compatibility-between-releases),
so a result is reproducible only with the version that made it.

## Further reading

The comparison page summarises
[what comparison studies have found](source-finder-comparison.md#what-comparison-studies-have-found)
and lists its [references](source-finder-comparison.md#references).
