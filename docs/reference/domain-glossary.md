# Source-finding domain glossary

**Status:** amended after the 2026-07-31 scientific pre-review; named human
review remains pending.

This glossary establishes Hebog's domain language and maps the current
Rapthor/PyBDSF/LSMTool vocabulary onto it. Definitions become stable only after
the [Rapthor source-finding contract](rapthor-source-finding-contract.md),
example products, and scientific thresholds are reviewed.

## Images and noise

| Term | Definition and naming guidance |
| --- | --- |
| Image | A two-dimensional radio-continuum pixel array plus WCS, beam, unit, and validity metadata. Qualify the scientific state when ambiguity is possible. |
| Primary-beam-uncorrected image | Image before primary-beam correction. Its noise is usually more nearly uniform across the field, making it the preferred detection/noise-estimation plane. Rapthor calls this `flat_noise_image`; “apparent sky” describes the physical state, not the canonical API field. |
| Primary-beam-corrected image | Estimate after primary-beam correction, used for intrinsic-flux measurements where the correction is valid. Rapthor calls this `true_sky_image`, but the product is not literal truth. Use `primary_beam_corrected` canonically and retain `true_sky` only at the adapter boundary. |
| Apparent sky | Sky brightness attenuated by the instrument response. It is represented by a primary-beam-uncorrected image or sky model. |
| Intrinsic sky estimate | Estimated sky brightness with the instrument attenuation removed. Never shorten this to “truth” when discussing an observed image. |
| Flat-noise image | The apparent-sky image used to estimate noise that is approximately uniform across the field. “Flat” describes the noise, not the sky or background. |
| Background | Slowly varying non-source image level estimated independently of RMS. The current Rapthor path requests a zero mean map, but Hebog keeps the concept explicit. |
| RMS | Local root-mean-square noise estimate in the image's physical unit. Use `rms`, not standard deviation, when describing this compatibility product. |
| RMS image | A materialised image whose pixels contain local RMS estimates aligned with the input image. Qualify its primary-beam state canonically; `flat_noise_rms` and `true_sky_rms` are Rapthor compatibility names. An input image copied to an RMS filename is not an RMS image. |
| Residual image | Image remaining after subtracting a current model. It is not synonymous with a background-subtracted or normalized image. |
| Normalized image | Internal dimensionless array `(image - background) / rms` used for signal-to-noise thresholding. Spell “normalized” only where matching an external API; Hebog prose otherwise uses British English. |
| Invalid pixel | A masked, non-finite, blanked, or otherwise excluded sample. Invalid pixels contribute to neither background/RMS statistics nor source measurements. |

## Detection and measurement

| Term | Definition and naming guidance |
| --- | --- |
| Detection threshold | Minimum normalized peak needed to seed or accept an island. This maps to PyBDSF `thresh_pix`. Rapthor strategies use 5 sigma while the helper fallback is 7.5 sigma; Hebog requires an explicit `detection_threshold_sigma`. |
| Island threshold | Lower normalized boundary used to decide island membership. This maps to `thresh_isl`. Rapthor uses 3 sigma normally, 4 sigma in early cycles, and 5 sigma only as the helper fallback; Hebog requires an explicit `island_threshold_sigma`. “Growth” and “flood” threshold are common external synonyms. |
| Pixel | One array sample. Array indexing is `(y, x)` even when external APIs expose pixel coordinates as `(x, y)`. |
| Island | Connected above-island-threshold pixels associated with at least one accepted detection peak. It is a segmentation object, not automatically one source. |
| Gaussian component | One fitted Gaussian belonging to a PyBDSF source. Use the full qualifier; bare `component` is ambiguous. |
| Source candidate | One catalogue-level association inferred to represent astrophysical emission. In the PyBDSF source-list model, one or more fitted Gaussians may be grouped into a source and an island may contain one or more sources. A detection is not established astrophysical truth. |
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
| Reference frequency | Frequency at which a component's reported flux and spectral model are defined. Use `reference_frequency_hz`; never compare channel or MFS fluxes without it. |
| Spectral model | Explicit rule, such as spectral-index coefficients and their convention, relating component flux to frequency. It belongs to a source or component record, not to an implicit filename convention. |
| Patch | Group of sky-model components used as a calibration direction. The current compatibility path groups surviving sky-model components by island. |
| Source catalogue | Materialised table of measured source rows. Hebog documentation uses “catalogue”; compatibility code may retain external names such as `source_catalog`. |
| Source-filtering mask | Image-aligned island mask used to retain and group sky-model components. Do not call it a clean mask; a clean mask controls deconvolution. |
| Materialised product | Closed, restartable file plus plain metadata. It must not contain an open FITS handle, mutable full-image object, or scheduler client. |
| Compatibility adapter | Boundary that maps Hebog's internal schema and terms to the filenames, fields, units, and empty behaviour required by Rapthor/LSMTool. ADR 006 fixes this as a versioned, dependency-free boundary. |

## Execution

| Term | Definition and naming guidance |
| --- | --- |
| Scientific kernel | Deterministic array operation independent of scheduler state and file lifecycle where practical. |
| Executor | Policy object that runs coarse scientific work serially, locally, or through an existing Dask client. It does not own Rapthor's top-level graph. |
| Port | Narrow typed protocol at a demonstrated boundary, such as execution, image input, or product output. A port describes a capability needed by the scientific pipeline; it is not a generic plugin registry. |
| Workflow adapter | Boundary that translates another pipeline's orchestration, configuration, product schema, and failure behaviour to and from Hebog's public scientific API. It depends on the core, never the reverse. |
| Native extension | Optional compiled Hebog module implemented outside Python, such as Rust or C++. Use “native” only for implementation language in this context; call ordinary Hebog outputs “Hebog-format products”. |
| FFI boundary | Foreign-function interface between Python/NumPy and a native extension. Its contract includes dtype, shape, strides, alignment, ownership, mutability, copying, errors, interpreter state, and thread budget. |
| Performance curve | Size-stratified record of complete latency, throughput, memory, and execution evidence across the frozen workload matrix. It is preferred to a single headline benchmark. |
| Execution crossover | Measured resource and workload boundary where a different valid executor, storage, partition, or batching plan becomes faster end to end. It is evidence-based, not a permanent image-size constant. |
| Admitted worker memory | RAM budget Rapthor makes available to one Hebog worker after reserving node headroom and concurrent pipeline demand. It may be substantially less than the hundreds of GB physically installed on a production node. |
| Serial reference | Deterministic Hebog execution used as the first oracle for local and Dask conformance. It is not the same as the PyBDSF compatibility oracle. |
| Partition manifest | Small, deterministic record describing a logical image's shape, tile cores, stage-specific halos, global coordinates, ownership, and chunk locations. It contains no image plane or scheduler object. |
| Product generation | One run-scoped set of intermediate Zarr product chunks. It is consumable only after an immutable completion manifest identifies exactly one validated chunk for every expected product and tile. A Zarr hierarchy without that marker is incomplete, even when its array metadata exists. |
| Tile core | Non-overlapping image region owned by one tile for output and source-assignment purposes. A small image is represented as one tile core. |
| Halo | Read-only pixels surrounding a tile core that provide neighbourhood context for windows, convolution, connectivity, or fitting. Qualify the stage and pixel width; halo pixels are not duplicate output ownership. |
| Boundary summary | Bounded metadata emitted by a tile for cross-tile reconciliation, such as mergeable statistics, connected-label equivalences, or edge-source state. It is proportional to a boundary or catalogue shard, not the full image. |
| Reconciliation | Deterministic merge of tile summaries into global statistics, stable labels, sources, catalogues, or products, normally through hierarchical reductions. |
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
- Prefer `primary_beam_uncorrected` and `primary_beam_corrected` in the
  scientific API. Keep `apparent_sky`, `true_sky`, and `flat_noise` only where
  their physical meaning or compatibility mapping is explicit.
- Give every frequency-dependent flux a unit and `reference_frequency_hz`,
  plus the spectral-model convention when applicable.
- Use `catalogue` in Hebog prose and internal modules. Preserve `catalog` in
  external field names and filenames when compatibility requires it.
- Use `serial`, `local`, and `dask` for executor modes. Do not use `parallel`
  as a mode name because it does not identify ownership or resource policy.
- Use `tile_y_index`, `tile_x_index`, `core_bounds`, and stage-qualified halo
  names such as `detection_halo_pixels`. Do not use “chunk” and “tile”
  interchangeably: a chunk is a storage unit; a tile is a scientific work and
  ownership unit.

## Legacy term map

| Current external name | Hebog concept |
| --- | --- |
| `thresh_pix` | Detection threshold |
| `thresh_isl` | Island threshold |
| `flat_noise_image` | Primary-beam-uncorrected detection/noise image |
| `true_sky_image` | Primary-beam-corrected image (legacy name; not truth) |
| `rms_box`, `rms_box_bright` | Normal and bright-source RMS window width/step |
| `island_mask` | Source-filtering mask |
| PyBDSF `srl` catalogue | Source catalogue compatibility view |
| `Source_id` | Compatibility source identifier |
| `Isl_Total_flux` | Compatibility island-integrated flux field |
| `filter_skymodel` | Cross-system behaviour that detects emission, filters/groups sky-model components, writes diagnostics products, and currently mixes PyBDSF with LSMTool |

Open vocabulary questions are tracked in the implementation plan. A domain
review must resolve them before the Phase 0 exit gate.
