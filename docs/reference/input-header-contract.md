# Input header contract

Hebog reads its physical description of an image from the FITS header. This
page says what the public finder reads, where each value may come from, and
how the headers that common radio imagers and pipelines write fare against
it. Every image is either accepted or refused before analysis, with an error
that names the keyword or layout at fault, or says that the file cannot be
read as a FITS image.

## What the finder reads

| Needed | Read from | When it is missing or unusable |
| --- | --- | --- |
| One image plane | The primary HDU. The last two axes are the plane; every other axis must have length one. | Refused, naming each longer axis, for example `SPECLNMF (NAXIS3 = 16)`. Channel, Stokes and other cubes need their own contract. |
| Stokes parameter | A `STOKES` axis's world value at the plane, so a writer that encodes it in `CRPIX` rather than `CRVAL` is read correctly. No `STOKES` axis means Stokes I. | Any parameter other than I is refused: Q, U and V, and instrumental planes such as `XX` or `RR`. A value that is not an integer parameter code, such as `1.4`, is refused as malformed. |
| Pixel values | The plane's pixels in any `BITPIX`. A stored value is scaled by `BSCALE` and `BZERO`. A stored integer equal to `BLANK` is an invalid pixel, as NaN is, and so is every pixel of a block of one repeated value; see [Invalid pixels](#invalid-pixels). | A file that ends before its last pixel is refused as truncated. `BSCALE`, `BZERO` and an integer image's `BLANK` must be numbers; see [Numbers](#numbers). |
| Pixel unit | `BUNIT`. `JY/BEAM` and other spellings of Jy/beam are accepted. | A supplied `brightness_unit`, else refused. The public finder measures `Jy/beam` only. A value without its quotes, which Astropy cannot parse, is refused. |
| Restoring beam | `BMAJ`, `BMIN` and `BPA`, in degrees. | A supplied value for each missing keyword, else refused. A card that is not a number is refused; see [Numbers](#numbers). A beam wider than 22 pixels (FWHM) is refused; see [Limitations](#limitations). |
| Reference frequency | `RESTFRQ`, then `RESTFREQ`, then the first `FREQ` axis's `CRVAL`. | A supplied `reference_frequency_hz`, else refused. A card that is not a number is refused. |
| Celestial WCS | Astropy's reading of the header: any projection it supports (`SIN`, `TAN`, `ZEA` and others), with `CDELT`, a `PC` or `CD` matrix, or a legacy `CROTA`. | Refused when absent. A card that is not a number, and a rotation Astropy would silently drop, are refused; see [Numbers](#numbers) and [Rotation](#rotation). |
| Coordinate frame | The celestial axis types, which must be `RA`/`DEC` or `GLON`/`GLAT`, then `RADESYS`, `EQUINOX` and `EPOCH`. With none of the three, the frame is ICRS, as the WCS standard defines. `EQUINOX` or `EPOCH` of 2000 without `RADESYS` is FK5 J2000. | Only ICRS and FK5 J2000 are accepted; the error names the frame found, such as `GALACTIC` or `FK4, equinox 1950`. Other celestial axes, such as ecliptic `ELON`/`ELAT` or supergalactic `SLON`/`SLAT`, are refused by their axis types, because Astropy would read ecliptic coordinates as ICRS. Catalogue positions are always ICRS. |
| Size | `NAXIS1` and `NAXIS2`. | Refused above 15,402 pixels on either side, and above 1,000,000 pixels in all when the shorter side is under 600. |

Supplied values come from `SuppliedImageMetadata` on the request. Each one
fills only a keyword the header lacks; supplying a value the header already
has is refused, so a supplied value never overrides an image's own
description. The diagnostics record every supplied value.

```python
supplied = hebog.SuppliedImageMetadata(
    reference_frequency_hz=144e6,
    brightness_unit="Jy/beam",
)
```

## Imager and pipeline conventions

The table describes what each writer puts in the header, from its source
code or documentation, and what the finder does with the header. Each row
has a fixture test in `tests/integration/test_input_header_contract.py`.
A header's result does not admit the image's size: an image larger than
15,402 pixels on either side is refused whatever its header. The whole
LoTSS-Deep DR2 ELAIS-N1 and MIGHTEE XMM-LSS images fit, as do LoTSS-DR3
mosaics up to that size, such as mosaic 1312; wider LoTSS-DR3 mosaics and the
full LOFAR-HD, GLEAM-X and SDC1 images need a cut-out until the envelope
reaches them.

| Writer | What the header holds | Result |
| --- | --- | --- |
| WSClean | Four axes: RA, Dec, `FREQ`, `STOKES`. `EQUINOX = 2000` without `RADESYS`; no `RESTFRQ`, so the frequency is the `FREQ` axis's centre; `BUNIT = 'JY/BEAM'`; beam in degrees. | Accepted as FK5 J2000. A polarisation product such as `-XX-image.fits` is refused as Stokes XX. |
| DDFacet restored image, including the LoTSS-Deep DR2 ELAIS-N1 apparent and true-sky images | Four axes with `STOKES` before `FREQ`; `RADESYS = 'ICRS'`; `RESTFRQ`; `BUNIT = 'Jy/beam'`; beam. | Accepted. |
| ddf-pipeline LoTSS mosaic (`mosaic_pointing.py`), including the LoTSS-DR2 and DR3 mosaics | Two axes; `RADESYS = 'ICRS'` and `EQUINOX = 2000`; `RESTFRQ = 144 MHz`; `BUNIT`; beam. | Accepted. |
| ddf-pipeline generic `mosaic.py` | Two axes; the beam copied from the first input image; no `BUNIT` and no frequency. | Supply `brightness_unit` and `reference_frequency_hz`. The copied beam describes the first input only. |
| LOFAR-HD ELAIS-N1 mosaics | Two axes; `BUNIT = 'JY/BEAM'`; beam; no frame or frequency keyword. | Read as ICRS; supply `reference_frequency_hz`. |
| CASA `exportfits` | Four axes: RA, Dec, `FREQ`, `STOKES`; a `PC` matrix; `RADESYS = 'FK5'` with `EQUINOX = 2000`, or ICRS; `RESTFRQ` when the image has one; `BUNIT`; beam. | Accepted. An image with per-plane beams (`CASAMBM = T` and a `BEAMS` table) has no primary-header beam and is refused unless the beam is supplied. |
| OSKAR imager | Three axes: RA, Dec, `FREQ`; `CROTA1` to `CROTA3` all zero; no `CUNIT`; `EQUINOX = 2000`; `BUNIT = 'JY/BEAM'`; no beam. | Supply the beam. OSKAR images are not deconvolved, so a supplied Gaussian stands in for the main lobe of the point-spread function. |
| SKA SDP data models (`export_to_fits`) | Four axes with `STOKES` before `FREQ`, the Stokes parameter encoded through `CRPIX`; `RADESYS = 'ICRS'`; beam when the image has a clean beam; no `BUNIT` or `RESTFRQ`. | Supply `brightness_unit`; the frequency comes from the `FREQ` axis. |
| Obit `MFImage` (MeerKAT SMGPS) | Four axes whose third, `SPECLNMF`, holds the broadband image in plane 1, then spectral-index and sub-band planes (16 in an SMGPS tile); `EPOCH` and `EQUINOX` without `RADESYS`; `BUNIT`; the beam only as `CLEANBMJ`, `CLEANBMN` and `CLEANBPA` and in AIPS history cards. | Refused as a cube. Plane 1 written as its own image is readable with the beam supplied from the `CLEAN` keywords, and the frequency too when Obit wrote no `RESTFREQ`. SMGPS mosaics are also in Galactic coordinates, which are refused. |
| MeerKAT MIGHTEE DR1 (WSClean and DDFacet, mosaicked with Montage) | Two axes in the `TAN` projection, yet `CTYPE3` and `CTYPE4` declare `FREQ` and `STOKES` axes with no `NAXIS3` or `NAXIS4`; `EQUINOX = 2000` without `RADESYS`; `BUNIT = 'Jy/beam'`; a circular beam. | Accepted as FK5 J2000, with the frequency from the declared `FREQ` axis. The survey's effective-frequency maps, which give each pixel's own frequency, are not read. |
| GLEAM-X DR1 mosaics (SWarp, then Miriad `fits`) | Two axes in the `ZEA` projection; `EPOCH = 2000`; `BUNIT` and beam copied from one input snapshot; the frequency in a non-standard `FREQ` keyword. | Read as FK5 J2000; supply `reference_frequency_hz`. The copied beam is not the mosaic's point-spread function, which the survey publishes as separate four-plane maps and which varies across the field; such a map is itself refused as a cube. |
| SKA Data Challenge 1 (Miriad) | Four axes; `EPOCH = 2000`; `BMAJ` and `BMIN` without `BPA`. | Read as FK5 J2000; supply `beam_position_angle_degrees`. |

## Numbers

Astropy and wcslib raise no error for a card that should hold a number and
holds something else. wcslib warns and reads the keyword's default in its
place, and a logical beam or frequency is read as the number one. A `CRVAL1`
of `'180.0'` would put every source at right ascension zero, a `CDELT1` of
`NAN` would make each pixel one degree wide, and a `BMAJ` of `T` would be a
one-degree beam. Hebog refuses such an image and names the keyword.

The rule covers the restoring beam (`BMAJ`, `BMIN` and `BPA`), the reference
frequency (`RESTFRQ` and `RESTFREQ`) and, on every axis, the numeric cards of
the WCS: `CRVALi`, `CRPIXi`, `CDELTi`, `CROTAi`, `PCi_j`, `CDi_j`, `PVi_m`
and its older spelling `PROJPn`, `LONPOLE`, `LATPOLE`, `EQUINOX` and
`EPOCH`. Each must hold one finite number. None of these does:

- text, including a quoted number such as `'180.0'` and an equinox written
  as `'J2000'`;
- a logical, `T` or `F`;
- a complex number;
- `NAN` or `INF`, which FITS has no way to write, or a number too large to
  hold, such as `1.0E999`; and
- a number followed by its unit, such as `180.0 deg` or `4 arcsec`, or
  anything else that is not one number.

A WCS card with no value is refused too. A beam or frequency card with no
value is a missing keyword, which a supplied value can fill.

The pixel scaling follows the same rule: `BSCALE` and `BZERO` must each hold
one finite number, and `BLANK`, on integer pixels, an integer, as FITS
requires. A scaling card with no value takes its FITS default. On
floating-point pixels FITS gives `BLANK` no meaning, and it is not read. A
scaling card that Astropy cannot parse at all stops the file from opening,
and is reported as a file that cannot be read.

A number is read in any spelling FITS allows. That includes the `D` exponent
that marks double precision, as in `1.8D+02`: wcslib on its own stops
reading at the letter and takes the value for 1.8, so Hebog gives it every
float in the header, among these cards or not, as Astropy read it.

## Rotation

The WCS standard reads a legacy `CROTAi` rotation from the latitude axis only,
and ignores it when a `PCi_j` or `CDi_j` matrix is present. Astropy follows
the standard without a warning, so two kinds of header would be read with
a different orientation than their writer intended, and every catalogue
position would move. Hebog refuses:

- a rotation on the longitude axis (`CROTA1` for RA in axis 1) that is not
  zero and differs from the latitude axis's; and
- a non-zero latitude-axis rotation beside a `PC` or `CD` matrix, in either
  its current spelling or the older `PC001001` form.

A zero rotation, a rotation on the latitude axis alone, and equal rotations
on both axes are unambiguous and accepted. OSKAR writes zeros; AIPS and Obit
write the rotation on the latitude axis.

## Invalid pixels

A pixel is invalid when:

- its value is NaN or infinite;
- it is a stored integer equal to `BLANK`; or
- it lies in a block of one repeated value: some 3×3 square of pixels that
  holds it holds one value. Every pixel of such a square is invalid, its
  edge as much as its centre.

An invalid pixel takes no part in the background, the noise, detection or
measurement, and the published RMS is NaN there. Imagers and mosaicking
tools mark a region they did not observe with NaN or with a constant, often
zero. A constant region is not noise: a noise window over it measures a
noise of zero, and one at its edge too little. PyBDSF's preprocessing stops
with "Clipped rms appears to be zero" only when the sigma-clipped RMS of the
whole image is about zero, as it can be for an image that is mostly zeros, and
then asks for such regions to be blanked with NaN or cut with `trim_box`; a
zero strip beside noise does not stop it. Hebog treats a block as blanked
whatever share of the image it covers.

A block is blanked to its last pixel, as NaN padding is, so it leaves no
step beside the data: a constant far from the noise, such as 1.0 Jy/beam
beside noise of 10⁻⁴, or zero padding beside noise whose mean lies well
below zero, publishes no island or source there. At the image edge a square
is clipped to the image: a pixel at the edge is the centre of a square of
one value when it equals the neighbours it has inside the image, five, or
three at a corner. A block therefore reaches the edge, and a constant strip
two pixels wide along an edge, or a 2×2 patch in a corner, is a block; a
strip one pixel wide is not, nor is a constant line two pixels wide inside
the image. NaN equals nothing, so a square that holds a NaN is not of one
value, but a NaN inside zero padding leaves no zero valid, because other
squares of zeros hold them. An image that is constant everywhere has no
valid pixel, as an all-NaN image has none, and publishes the same empty
products. Noise stored in steps much finer than its RMS does not repeat one
value over nine pixels; an integer image quantized about as coarsely as its
noise loses pixels to the rule (17% of one whose noise is about half a
quantum).

The rule is one function, `hebog.io.pixel_validity.valid_input_pixels`. A
pixel's validity depends on the pixels up to two away, so each window is
judged from a read two pixels wider than itself, and the rule does not
depend on how the image is tiled.

## Limitations

- **One beam.** Hebog applies one restoring beam, evaluated in pixels at the
  image centre, to the whole image. A mosaic whose inputs have different
  resolutions, or a wide `ZEA` mosaic whose projection changes the beam's
  pixel shape across the field, is not described by one beam. Measuring that
  effect and deciding how to handle a point-spread function that varies
  across the field is the plan's task 15.
- **Frame defaults.** A header with no frame keyword is ICRS. If its writer
  meant FK5 J2000, positions differ by the frame tie between the two, a few
  tens of milliarcseconds.
- **Header only.** The contract checks what the header states, not whether
  it is true: a wrong `BUNIT` or beam is read as written.
- **Narrow images.** An image whose shorter side is under 600 pixels may
  hold at most 1,000,000 pixels. The 150-pixel background meshes do not fit
  across so narrow a strip, and what replaces them reads the whole image in
  one task, which is bounded at that size.
- **Beam sampling.** A restoring beam wider than 22 pixels (FWHM, major
  axis) is refused. Local noise is refined from a window that grows with
  the beam, and 22 is the largest whole number of pixels whose window stays
  within its bound of 1,000,000 pixels. The limit is not a measure of where the finder
  is valid: the background and noise meshes are fixed in pixels, and in
  tests with beams of 18 to 20 pixels it has missed bright sources. Which
  sampling to support is the plan's task 62.
- **Repeated keywords.** FITS does not define a keyword that appears twice,
  and Hebog does not refuse one. The WCS, including a frequency taken from
  its `FREQ` axis, is read from the last card of a repeated keyword, as
  wcslib reads it. The beam and `RESTFRQ` are read from the first, as Astropy
  reads them.

## Sources

The conventions above were read on 27 September 2026 from the writers'
source code: WSClean's FITS writer in `aocommon`
(`include/aocommon/fits/fitswriter.h`) and `wsclean/io/wscfitswriter.cpp`;
DDFacet's `DDFacet/Imager/ClassCasaImage.py`; ddf-pipeline's
`scripts/mosaic.py` and `scripts/mosaic_pointing.py`; OSKAR's
`oskar/imager/src/private_imager_create_fits_files.c`; the SKA SDP data
models' `image_create.py` and `image_model.py`; Obit's `ObitImageMF.c`,
`ObitImageUtil.c` and `ObitIOImageFITS.c`, with Obit memo 63 and the SMGPS
data-release paper (Goedhart et al. 2024); casacore's
`ImageFITS2Converter.cc` and `FITSCoordinateUtil.cc`; and the GLEAM-X
pipeline's SWarp templates. Headers read from the images themselves
confirm the LoTSS-DR2 and DR3, SDC1 and LOFAR-HD entries (16 September) and
the MIGHTEE DR1, GLEAM-X DR1, SMGPS and LoTSS-Deep DR2 entries
(28 September).
