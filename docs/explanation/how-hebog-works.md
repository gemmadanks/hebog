# How Hebog finds radio-continuum sources

This page follows one call to `hebog.find_sources()` from a FITS image to its
four published products. Every box corresponds to behaviour in the public
finder. The
[public-products reference](../reference/public-products.md) defines the
resulting fields, units, nulls, and scientific interpretation.

Hebog separates three ideas that are easy to conflate:

- an **island** is a connected footprint in the published detection mask;
- a **Gaussian component** is a successfully fitted Gaussian model; and
- a **source** is Hebog's image-domain association of one or more detection
  components.

None of these is automatically an astrophysical object or a sky-model
component. An island may contain multiple independent sources, a source may
span multiple disconnected islands, and a detected component may have no
Gaussian row when its fit is unavailable.

## End-to-end decision flow

```mermaid
flowchart TD
    start([SourceFinderRequest, configuration, executor])
    config{Configuration valid?}
    destination{Output directory absent?}
    input{FITS readable and metadata supported?}
    reject_config([Reject invalid thresholds or profile])
    reject_destination([Refuse to overwrite caller-owned output])
    reject_input([Reject invalid unit, WCS, beam, frequency, shape, or size])

    start --> config
    config -- No --> reject_config
    config -- Yes --> destination
    destination -- No --> reject_destination
    destination -- Yes --> input
    input -- No --> reject_input
    input -- Yes --> partition[Plan deterministic 128 x 128 detection tiles]

    profile{Continuum or compact profile?}
    continuum[Source-protected background and adaptive local RMS]
    compact[Compact-profile background and RMS policy]
    rms[Reconcile tile estimates into background and RMS planes]
    usable{Any finite, positive RMS?}
    empty[Create empty catalogue, zero mask, and all-NaN unavailable RMS]

    partition --> profile
    profile -- Continuum --> continuum
    profile -- Compact --> compact
    continuum --> rms
    compact --> rms
    rms --> usable
    usable -- No --> empty

    residual[Subtract background; exclude invalid pixels; divide by local RMS]
    filters[Evaluate beam-aware matched filters and residual B3 à trous scales]
    flood[Grow eight-connected candidate islands on original residual pixels at island threshold]
    seed{Candidate has detection-threshold evidence?}
    drop_unseeded[Discard unseeded region]
    area{Meets multiscale area rule or has a direct detection-threshold pixel?}
    drop_area[Discard unsupported sub-area region]
    own[Keep direct labels; assign nearby significant multiscale support to nearest seed owner]
    boundary[Refine boundaries with original-pixel S/N and adjacent-scale persistence; preserve owner bridges]
    configured_size{Within caller minimum and optional maximum pixel count?}
    drop_size[Discard component]
    any_component{Any component remains?}

    usable -- Yes --> residual
    residual --> filters
    filters --> flood
    flood --> seed
    seed -- No --> drop_unseeded
    seed -- Yes --> area
    area -- No --> drop_area
    area -- Yes --> own
    own --> boundary
    boundary --> configured_size
    configured_size -- No --> drop_size
    configured_size -- Yes --> any_component
    any_component -- No --> empty

    deblend{Parent is eligible for bounded deblending and has separable peaks?}
    split[Split into deterministic component owners]
    preserve[Keep one owner or record bounded-work deferral]
    fit{Gaussian model is measurable and scientifically admissible?}
    gaussian[Retain admitted Gaussian-component measurement]
    fit_absent[Keep detection identity; record unavailable or deferred fit]
    hierarchy[Build multiscale component hierarchy and association evidence]
    association{Profile allows source association?}
    associate[Choose independent, compact-model, or extended-morphology grouping]
    singleton[Use one source per component; declare extended-emission limitation]
    source_measure[Measure each source once with signed, non-overlapping owned aperture]
    source_valid{Positive, available source measurement with publication support?}
    compact_valid{Admitted component measurement with publication support?}
    source_row[Publish source row]
    source_absent[Keep source disposition without a catalogue row]

    any_component -- Yes --> deblend
    deblend -- Yes --> split
    deblend -- No --> preserve
    split --> fit
    preserve --> fit
    fit -- Yes --> gaussian
    fit -- No --> fit_absent
    gaussian --> hierarchy
    fit_absent --> hierarchy
    hierarchy --> association
    association -- Continuum --> associate
    association -- Compact --> singleton
    associate --> source_measure
    singleton --> compact_valid
    source_measure --> source_valid
    source_valid -- Yes --> source_row
    source_valid -- No --> source_absent
    compact_valid -- Yes --> source_row
    compact_valid -- No --> source_absent

    assemble[Build mask-connected islands and link sources and fitted components]
    bundle[Write and validate catalogue, RMS, mask, and diagnostics in a private bundle]
    publish{All four products valid?}
    success([Atomically rename complete bundle and return SourceFinderResult])
    fail([Leave requested output absent; caller may retry])

    source_row --> assemble
    source_absent --> assemble
    empty --> bundle
    assemble --> bundle
    bundle --> publish
    publish -- Yes --> success
    publish -- No --> fail
```

The diagram has two kinds of rejection. Input and configuration failures stop
before scientific work. Scientific non-admission does not normally abort the
run: an unseeded region, a rejected fit, or an unavailable source measurement
is omitted from the corresponding catalogue population and is represented in
diagnostics where an identity was established.

## What each stage means

### 1. Admit a physically interpretable image

The public finder accepts one two-dimensional image, or a FITS image with only
singleton axes before its final two spatial axes. It currently requires
`BUNIT=Jy/beam`, an ICRS celestial WCS, a finite positive restoring beam, a
positive reference frequency, and no more than 1,024 pixels along either
spatial axis. NaN pixels are allowed and excluded. The 1,024-pixel limit is a
current public-preview limit, not Hebog's target architecture.

The detection/background stage uses deterministic 128-by-128 tile cores and
can run through either the serial executor or a caller-supplied Dask client.
Later measurement stages operate on the complete admitted image, which is why
the size limit matters. Hebog does not create a Dask cluster and scientific
ownership does not depend on task order.

### 2. Estimate background and local noise

Hebog estimates the slowly varying background independently of the RMS. It
uses robust window statistics, excludes invalid samples, protects candidate
source support, interpolates missing cells, and reconciles the bounded tile
results. In the continuum profile, eligible images use a finer RMS estimate
around protected emission; the compact profile does not claim
complete extended-emission handling.

If no finite positive RMS estimate exists anywhere, sigma thresholding is not
scientifically defined. Hebog returns a successful, explicit empty result:
the catalogue has no rows, the mask is zero, and `rms.fits` is all NaN with
scientific status `unavailable`. This is **not** evidence that the image
contains no emission.

### 3. Detect compact and multiscale emission

On scientifically valid pixels Hebog forms the residual
`image - background` and its local signal-to-noise ratio. It also evaluates a
beam-aware matched-filter bank and a residual B3 à trous representation. The
filtered representations help decide whether emission is significant; the
initial flood itself grows over eight-connected original-residual pixels at
the caller's lower island threshold.

A flooded region needs evidence at the higher detection threshold. A
filter-promoted region must also satisfy the beam-area rule; a region
with a direct original-pixel detection-threshold sample can survive below that
multiscale area. Hebog then applies the caller's explicit minimum and optional
maximum pixel count, so the two area decisions serve different purposes.

Direct residual labels establish stable component identity. Significant
multiscale support may enlarge the measurement owner within a bounded beam
radius, but it is assigned to the nearest direct owner and cannot merge two
direct identities merely because their diffuse support touches. Publication
boundaries are rechecked using original-pixel S/N, adjacent-scale persistent
support, and connectivity-preserving owner bridges.

### 4. Deblend and fit components

Hebog searches retained parents for sufficiently separated, significant peaks
and can divide overlapping emission into deterministic owned regions. Hard
bounds limit inseparable fitting work. If a parent cannot safely enter the
bounded deblend or joint-fit path, Hebog preserves the detection and records a
deferral instead of silently dropping it or allowing unbounded work.

Each measurable component receives moment initialization and a bounded joint
Gaussian fit against original, background-subtracted pixels. Model admission
checks convergence, physical bounds, information conditioning, residual
adequacy, visibility, and uncertainty availability. Depending on the data,
the selected model can be free elliptical, beam constrained, or
centroid-constrained elliptical. Only admitted fits appear in
`GAUSSIAN_COMPONENTS`; every established component still has a diagnostic
disposition.

### 5. Associate and measure sources

For the continuum profile, Hebog builds a hierarchy from per-scale features
and records the evidence for any multi-component merge. Compact-model and
extended-morphology evidence can constrain the final membership; an
unconfirmed hierarchy remainder leaves components independent. In the compact
profile, each successfully measured component becomes its own source and
diagnostics explicitly declare `extended-emission-incomplete`.

Continuum-profile source photometry is deliberately not copied from a member
Gaussian. Hebog
assigns every observable pixel to at most one source aperture, sums signed
background-subtracted pixels, and reports that source-owned aperture
measurement. Measurement-only persistent wings can contribute flux without
moving the source position support. Position selection retains both the signed
original and denoised estimates in diagnostics, including the rule used. A
non-positive or unavailable signed source measurement is not replaced with a
positive-only estimate; its disposition remains, but no source row is
published. In the compact profile, a source row deliberately carries the same
Gaussian-model measurement as its one component; it does not claim an
extended-source aperture measurement.

### 6. Assemble and publish products

The source-filtering mask is the retained detection support. Hebog labels its
eight-connected footprints to create the catalogue's `ISLANDS` population,
then links the independently constructed source associations. A successful
Gaussian fit is published only when its parent source row is also published.
This final construction is why an island, a source, and a fit must not be
counted interchangeably.

All products are written and validated in a private sibling directory. Only a
complete four-file bundle is renamed to the caller's output directory. Hebog
never overwrites an existing destination. A failed run leaves the requested
destination absent and can be retried with the same request.

## A non-expert's mental model

For pipeline developers, the simplest safe model is:

1. the FITS image is the immutable input;
2. `SourceFinderConfig` states the scientific thresholds and profile;
3. the executor states **where** coarse work runs, not **what** the science
   means;
4. `SourceFinderResult` is small metadata pointing to four closed files; and
5. the catalogue and diagnostics must be considered together.

Do not infer a Gaussian fit from a source row, treat a blank catalogue as proof
of a blank sky, or infer scientific qualification from a successful call. Use
the product records and Hebog readers to verify role, schema, byte identity,
and availability before downstream processing.

Hebog does not publish its background plane, normalized residual,
multiscale planes, component-label image, deblended model/residual images, or a
filtered sky model. Those are internal scientific states or responsibilities
of the integrating workflow.
