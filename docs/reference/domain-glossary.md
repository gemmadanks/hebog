# Source-finding domain glossary

**Status:** provisional for Phase 0 review.

This glossary establishes Hebog's domain language and maps the current
Rapthor/PyBDSF/LSMTool vocabulary onto it. Definitions become stable only after
the [Rapthor source-finding contract](rapthor-source-finding-contract.md),
example products, and scientific thresholds are reviewed.

## Images and noise

| Term | Definition and naming guidance |
| --- | --- |
| Image | A two-dimensional radio-continuum pixel array plus WCS, beam, unit, and validity metadata. Qualify the scientific state when ambiguity is possible. |
| Apparent sky | Sky brightness attenuated by the instrument response. Rapthor's non-primary-beam-corrected image has comparatively flat noise and is the current `flat_noise_image`. |
| True sky | Estimated intrinsic sky brightness after primary-beam correction. Use `true_sky` explicitly; never call this merely the corrected image. |
| Flat-noise image | The apparent-sky image used to estimate noise that is approximately uniform across the field. “Flat” describes the noise, not the sky or background. |
| Background | Slowly varying non-source image level estimated independently of RMS. The current Rapthor path requests a zero mean map, but Hebog keeps the concept explicit. |
| RMS | Local root-mean-square noise estimate in the image's physical unit. Use `rms`, not standard deviation, when describing this compatibility product. |
| RMS image | A materialised image whose pixels contain local RMS estimates aligned with the input image. Qualify it as `flat_noise_rms` or `true_sky_rms`. |
| Residual image | Image remaining after subtracting a current model. It is not synonymous with a background-subtracted or normalized image. |
| Normalized image | Internal dimensionless array `(image - background) / rms` used for signal-to-noise thresholding. Spell “normalized” only where matching an external API; Hebog prose otherwise uses British English. |
| Invalid pixel | A masked, non-finite, blanked, or otherwise excluded sample. Invalid pixels contribute to neither background/RMS statistics nor source measurements. |

## Detection and measurement

| Term | Definition and naming guidance |
| --- | --- |
| Detection threshold | Minimum normalized peak needed to seed or accept an island. This maps to PyBDSF `thresh_pix`, currently 7.5 sigma; prefer `detection_threshold` in Hebog. |
| Island threshold | Lower normalized boundary used to decide island membership. This maps to `thresh_isl`, currently 5.0 sigma; prefer `island_threshold`. |
| Pixel | One array sample. Array indexing is `(y, x)` even when external APIs expose pixel coordinates as `(x, y)`. |
| Island | Connected above-island-threshold pixels associated with at least one accepted detection peak. It is a segmentation object, not automatically one source. |
| Gaussian component | One fitted Gaussian belonging to a PyBDSF source. Use the full qualifier; bare `component` is ambiguous. |
| Source | One astrophysical detection record. In the PyBDSF source-list model, one or more fitted Gaussians may be grouped into a source, and an island may contain one or more sources. |
| Catalogue row | Serialized representation of one source in the compatibility source-list catalogue. A row is data interchange, not the in-memory domain object. |
| Compact source | Detection sufficiently unresolved or small for the reviewed compact-source measurement and comparison rules. State the size criterion when using it in a test. |
| Blended source | Two or more physically distinct sources whose above-threshold emission overlaps and requires deblending. |
| Extended emission | Emission whose structure is not adequately represented as one beam-sized component. |
| Multiscale emission | Emission detected or represented at more than one spatial scale. PyBDSF's wavelet pass is the current compatibility evidence. |

## Sky models and products

| Term | Definition and naming guidance |
| --- | --- |
| Clean component | Component written by the deconvolver, currently WSClean, before source-finder filtering. It is not a Gaussian component fitted by the source finder. |
| Sky-model component | One row in a makesourcedb/WSClean sky model used for prediction or calibration. Always qualify it when “component” could mean a Gaussian fit. |
| Patch | Group of sky-model components used as a calibration direction. The current compatibility path groups surviving sky-model components by island. |
| Source catalogue | Materialised table of measured source rows. Hebog documentation uses “catalogue”; compatibility code may retain external names such as `source_catalog`. |
| Source-filtering mask | Image-aligned island mask used to retain and group sky-model components. Do not call it a clean mask; a clean mask controls deconvolution. |
| Materialised product | Closed, restartable file plus plain metadata. It must not contain an open FITS handle, mutable full-image object, or scheduler client. |
| Compatibility adapter | Boundary that maps Hebog's internal schema and terms to the filenames, fields, units, and empty behaviour required by Rapthor/LSMTool. Its final design is an open ADR-005 decision. |

## Execution

| Term | Definition and naming guidance |
| --- | --- |
| Scientific kernel | Deterministic array operation independent of scheduler state and file lifecycle where practical. |
| Executor | Policy object that runs coarse scientific work serially, locally, or through an existing Dask client. It does not own Rapthor's top-level graph. |
| Serial reference | Deterministic Hebog execution used as the first oracle for local and Dask conformance. It is not the same as the PyBDSF compatibility oracle. |
| True-sky branch | Detection, measurement, catalogue, mask, and true-sky RMS work driven by the true-sky image when beam information is available. |
| Flat-noise branch | Independent RMS-estimation work driven by the flat-noise image. It may run concurrently only within the admitted memory budget. |

## Naming conventions

- Use `(y, x)` for NumPy array shapes and indices. Use explicit names such as
  `x_pixel` and `y_pixel` when an external WCS interface takes `(x, y)`.
- Put coordinate frame and unit in public names where the type does not carry
  them: for example, `ra_deg`, `dec_deg`, `major_axis_deg`, `beam_fwhm_deg`,
  `frequency_hz`, and `flux_jy` or `flux_jy_per_beam`.
- Use `detection_threshold` and `island_threshold` internally. Preserve
  `thresh_pix` and `thresh_isl` only in a compatibility or command boundary.
- Qualify every ambiguous component as `gaussian_component`,
  `clean_component`, or `sky_model_component`.
- Do not use `source`, `island`, `Gaussian component`, `catalogue row`, and
  `sky-model component` interchangeably.
- Keep `apparent_sky`, `true_sky`, `flat_noise`, `background`, `rms`, and
  `residual` explicit in filenames and public fields.
- Use `catalogue` in Hebog prose and internal modules. Preserve `catalog` in
  external field names and filenames when compatibility requires it.
- Use `serial`, `local`, and `dask` for executor modes. Do not use `parallel`
  as a mode name because it does not identify ownership or resource policy.

## Legacy term map

| Current external name | Hebog concept |
| --- | --- |
| `thresh_pix` | Detection threshold |
| `thresh_isl` | Island threshold |
| `rms_box`, `rms_box_bright` | Normal and bright-source RMS window width/step |
| `island_mask` | Source-filtering mask |
| PyBDSF `srl` catalogue | Source catalogue compatibility view |
| `Source_id` | Compatibility source identifier |
| `Isl_Total_flux` | Compatibility island-integrated flux field |
| `filter_skymodel` | Cross-system behaviour that detects emission, filters/groups sky-model components, writes diagnostics products, and currently mixes PyBDSF with LSMTool |

Open vocabulary questions are tracked in the implementation plan. A domain
review must resolve them before the Phase 0 exit gate.
