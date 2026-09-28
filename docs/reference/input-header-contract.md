# Input header contract

Hebog reads its physical description of an image from the FITS header. This
page says what the public finder reads, where each value may come from, and
how the headers that common radio imagers and pipelines write fare against
it. Every image is either accepted or refused before analysis, with an error
that names the keyword or layout at fault.

## What the finder reads

| Needed | Read from | When it is missing or unusable |
| --- | --- | --- |
| One image plane | The primary HDU. The last two axes are the plane; every other axis must have length one. | Refused, naming each longer axis, for example `SPECLNMF (NAXIS3 = 16)`. Channel, Stokes and other cubes need their own contract. |
| Stokes parameter | A `STOKES` axis's world value at the plane, so a writer that encodes it in `CRPIX` rather than `CRVAL` is read correctly. No `STOKES` axis means Stokes I. | Any parameter other than I is refused: Q, U and V, and instrumental planes such as `XX` or `RR`. |
| Pixel unit | `BUNIT`. `JY/BEAM` and other spellings of Jy/beam are accepted. | A supplied `brightness_unit`, else refused. The public finder measures `Jy/beam` only. |
| Restoring beam | `BMAJ`, `BMIN` and `BPA`, in degrees. | A supplied value for each missing keyword, else refused. |
| Reference frequency | `RESTFRQ`, then `RESTFREQ`, then the first `FREQ` axis's `CRVAL`. | A supplied `reference_frequency_hz`, else refused. |
| Celestial WCS | Astropy's reading of the header: any projection it supports (`SIN`, `TAN`, `ZEA` and others), with `CDELT`, a `PC` or `CD` matrix, or a legacy `CROTA`. | Refused when absent. A rotation Astropy would silently drop is refused; see [Rotation](#rotation). |
| Coordinate frame | `RADESYS`, `EQUINOX` and `EPOCH`. With none of them, the frame is ICRS, as the WCS standard defines. `EQUINOX` or `EPOCH` of 2000 without `RADESYS` is FK5 J2000. | Only ICRS and FK5 J2000 are accepted; the error names the frame found, such as `GALACTIC` or `FK4, equinox 1950`. Catalogue positions are always ICRS. |
| Size | `NAXIS1` and `NAXIS2`. | Refused above 10,000 pixels on either side. |

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
code or documentation, and what the finder does with it. Each row has a
fixture test in `tests/integration/test_input_header_contract.py`.

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

## Rotation

The WCS standard reads a legacy `CROTAi` rotation from the latitude axis only,
and ignores it when a `PCi_j` or `CDi_j` matrix is present. Astropy follows
the standard without a warning, so two kinds of header would be read with a
different orientation than their writer intended, and every catalogue
position would move. Hebog refuses both:

- a rotation on the longitude axis (`CROTA1` for RA in axis 1) that is not
  zero and differs from the latitude axis's; and
- a non-zero latitude-axis rotation beside a `PC` or `CD` matrix, in either
  its current spelling or the older `PC001001` form.

A zero rotation, a rotation on the latitude axis alone, and equal rotations
on both axes are unambiguous and accepted. OSKAR writes zeros; AIPS and Obit
write the rotation on the latitude axis.

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
