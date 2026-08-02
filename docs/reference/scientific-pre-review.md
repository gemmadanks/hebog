# Scientific pre-review findings

**Status:** first-pass technical/scientific review completed 2026-07-31; its
recommended amendments were approved in the named
[Phase 3 scientific review](phase-3-review-record.md) on 2026-08-02.

This review compares Hebog's provisional language and gates with official
source-finder and observatory documentation, published comparison studies, and
the Rapthor implementation at
`b1a64674b1022476cf052fc2d06ee3b16f031ecd`. Rapthor is treated as the first
compatibility consumer, not as scientific ground truth.

## Cross-pipeline consensus

| Topic | Finding for Hebog |
| --- | --- |
| Detection profile | A `5 sigma` seed or peak threshold is a common starting profile. PyBDSF and ASKAPsoft/Selavy commonly grow islands to `3 sigma`; Aegean defaults to a `4 sigma` flood threshold. These are configurable operating points, not universal scientific constants. |
| Background and noise | Local background and RMS estimation, source exclusion or clipping, and smaller windows near bright emission are established practice. Window sizes and interpolation must be selected in beam-aware and survey-aware terms rather than copied blindly between instruments. |
| Primary-beam state | Detection is commonly performed on the primary-beam-uncorrected image because its noise is more nearly uniform. Primary-beam-corrected data are then needed for intrinsic-flux work. A corrected image remains an estimate, not a literal “true sky”. |
| Domain objects | Islands, fitted components, associated sources, deconvolver clean components, and calibration sky-model components are distinct. Observatory catalogues often retain both source/component and island identifiers rather than collapsing these concepts. |
| Catalogue schema | Coordinate frame, epoch, units, reference frequency, source and component identifiers, shape convention, and spectral model must be explicit. Hebog's canonical records should align with SKA data-model naming and expose legacy PyBDSF or LSMTool columns only through adapters. |
| Scientific validation | No source finder is the truth oracle. Completeness and reliability must be evaluated against injected or otherwise governed truth, stratified by SNR, morphology, blending, field position, noise regime, and source density. Low-SNR differences must be reported as curves with uncertainty. |
| Distribution | Parallel source finding must test partition-boundary bias and reproduce a serial result. Published comparisons identify edge and chunk statistics as a source of bias; this supports Hebog's halo and deterministic-reconciliation rules. |
| Multiple frequencies | Per-channel images and an MFS image are different products. A source measurement needs a reference frequency and spectral model; cross-channel association must not silently turn one astrophysical source into unrelated rows. A first implementation may qualify MFS only, but must reject unsupported cubes or channel sets explicitly. |

## Rapthor findings and disagreements

The following observations are either inconsistent inside Rapthor or differ
from the broader conventions above.

1. **Operational thresholds differ from helper defaults.** Rapthor's
   `filter_image_skymodel` helper defaults to detection/island thresholds of
   `7.5/5.0`. Its built-in imaging and later self-calibration strategies pass
   `5.0/3.0`, while initial and early cycles pass `5.0/4.0`. The retained rich
   Prefect demo also uses `5.0/3.0`. Therefore `7.5/5.0` is a fallback API
   profile, not the representative production profile.
2. **The original Phase 0 baselines exercised the wrong profile and trusted
   declared provenance.** They used `7.5/5.0`. The reference image also
   contained an older LSMTool `bdsf.py` matching commit `4604b01`, despite
   Rapthor declaring `3adf3d6`. Corrected campaigns now require `5.0/3.0`,
   mount exact clean Rapthor and LSMTool checkouts, and verify imported code.
3. **“True sky” is too strong.** Rapthor uses this label for the
   primary-beam-corrected image and model. Hebog should use
   `primary_beam_corrected` canonically and retain `true_sky` only as a
   documented adapter alias.
4. **Blank-image RMS files are placeholders, not RMS estimates.** On the
   all-blank exception path Rapthor copies input images to RMS filenames.
   Hebog must not describe those pixels as RMS. It should emit a valid empty or
   invalid RMS product with explicit status, then reproduce copied files only
   if a versioned compatibility mode genuinely requires them.
5. **The no-island dummy component is not a scientific detection.** LSMTool's
   negligible central component is a legacy serialization workaround. Hebog's
   core result should contain zero sources; any dummy row belongs only in a
   compatibility writer and must be identifiable as synthetic.
6. **The filtering mask is optional in the current flow.** Rapthor returns no
   mask when the expected file is absent, although earlier Hebog documentation
   called it mandatory. Hebog's normal scientific result can always
   materialize a valid mask; the Rapthor adapter must model the legacy product
   as optional.
7. **Released and master PyBDSF disagree on the representative image.** Under
   the corrected matched `5.0/3.0` profile, release produces 12 source rows and
   pinned master produces 14, while the compact high-SNR case agrees exactly.
   This is most likely algorithm-version sensitivity in multiscale fitting or
   grouping, and is not evidence that either count is scientifically correct.

## Recommended amendments

- Keep detection and island thresholds explicit in the public request. Adopt
  `5.0/3.0` as the named Rapthor normal-cycle compatibility profile after human
  confirmation, with a separate `5.0/4.0` early-cycle profile. Do not make one
  of them a pipeline-neutral library default.
- Use `primary_beam_uncorrected_image` and
  `primary_beam_corrected_image` in the scientific API. Document
  `flat_noise_image` and `true_sky_image` as Rapthor aliases.
- Design the canonical catalogue around explicit source, component, and island
  identities, ICRS position, epoch, flux unit, reference frequency, spectral
  model, fitted and deconvolved shape, local RMS, and quality flags. Produce a
  PyBDSF source-list compatibility view separately.
- Define empty catalogue, mask, RMS, and diagnostics products scientifically
  in the core. Isolate dummy components and copied pseudo-RMS files behind an
  opt-in, versioned compatibility behavior if Rapthor cannot yet migrate.
- Replace the single `98%` compatibility target at `SNR >= 5` with
  completeness and reliability curves against governed truth, confidence
  intervals, and a reviewer-approved non-inferiority margin. Keep PyBDSF row
  recovery as a separately labelled compatibility metric.
- Report source, fitted-component, island, and sky-model retention comparisons
  separately. Break all scientific gates out by compact, blended, extended,
  edge, low-SNR, and varying-noise cases.
- Qualify MFS first if that is the first Rapthor need. Before accepting
  WSClean `-channels-out > 1`, specify channel association, per-plane beams,
  reference-frequency fluxes, spectral fitting, non-detections, and catalogue
  output semantics through a separate decision and test matrix.

## Gate assessment

The high-SNR astrometry, flux, RMS, and retained-component values in the plan
are reasonable initial engineering targets but are not established community
standards. Their confidence rule, matching population, component level, and
truth source require human approval. In particular, a hard 5-sigma detector
cannot be expected to recover a fixed 98% of sources whose *true* peak SNR is
exactly five after noise fluctuations, masking, blending, and local-RMS error.
Published source-finder challenges show the expected decline and trade-off in
completeness and reliability below roughly 10 sigma.

The first-pass recommendation was therefore **amend before scientific
approval**, not reject the architecture. The 2026-08-02 named review approved
the amended terminology, compatibility profiles, low-SNR treatment, compact
Phase 3 margins, and explicit deferrals. Later catalogue, multiscale,
production, and cutover claims retain their own evidence and review gates.

## Sources reviewed

- [PyBDSF processing documentation](https://pybdsf.readthedocs.io/en/latest/process_image.html)
- [ASKAPsoft continuum source-finding pipeline](https://yandasoft.readthedocs.io/en/latest/pipelines/ContinuumSourcefinding.html)
- [ASKAPsoft Selavy source-finding concepts and outputs](https://www.atnf.csiro.au/computing/software/askapsoft/sdp/docs/current/analysis/selavy.html)
- [AegeanTools documentation](https://aegeantools.readthedocs.io/_/downloads/en/latest/pdf/)
- [SKA SDP SkyComponent data model](https://developer.skao.int/projects/ska-sdp-datamodels/en/latest/data_model_api/sky_component_api.html)
- [SKA Global Sky Model LSM schema](https://developer.skao.int/projects/ska-sdp-global-sky-model/en/latest/design/lsm-file-structure.html)
- [WSClean primary-beam correction](https://wsclean.readthedocs.io/en/latest/primary_beam_correction.html)
- [WSClean component lists](https://wsclean.readthedocs.io/en/latest/component_list.html)
- [WSClean channel and MFS image products](https://wsclean.readthedocs.io/en/latest/making_image_cubes.html)
- [NRAO CASA imaging guide](https://casaguides.nrao.edu/index.php?title=First_Look_at_Imaging_CASA_6.4)
- [ASKAP/EMU source-finding data challenge](https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/askapemu-source-finding-data-challenge/A6C846F3ABB0105F026E3BD6B6EB9D19)
- [Hydra multi-source-finder comparison](https://www.cambridge.org/core/journals/publications-of-the-astronomical-society-of-australia/article/hydra-i-an-extensible-multisourcefinder-comparison-and-cataloguing-tool/08C33C6281B8566BBE9CF00045701F57)
- [LOFAR Deep Fields PyBDSF source catalogue columns](https://www.lofar-surveys.org/public/deepfields/data_release/en1/en1_columns_pybdsf_source.md)
