# ruff: noqa: C901, E501, N803, PLR0915

import marimo

__generated_with = "0.23.16"
app = marimo.App(width="full")


@app.cell(hide_code=True)
def _():
    import marimo as mo

    return (mo,)


@app.cell(hide_code=True)
def _():
    import dataclasses
    import json
    import math
    from pathlib import Path

    import matplotlib.pyplot as plt
    import numpy as np
    import numpy.typing as npt
    from astropy.io import fits
    from astropy.wcs import WCS

    from hebog.validation.comparison import CatalogueSource
    from hebog.validation.datasets import DatasetRecord, load_dataset_manifest
    from hebog.validation.external_runners import load_external_run_result
    from hebog.validation.materialization import load_external_input_bundle
    from hebog.validation.products import (
        load_aegean_catalogue,
        load_comparison_catalogue,
        load_fits_plane,
        load_pybdsf_catalogue,
    )
    from hebog.validation.support_diagnostics import (
        compare_support_component,
        rank_reference_support_disagreements,
    )
    from hebog.validation.support_plotting import (
        plot_support_component_diagnostic,
        read_beam_geometry,
    )

    @dataclasses.dataclass(frozen=True, slots=True)
    class CampaignCase:
        """One campaign image and its available source-finder runs."""

        key: str
        label: str
        case_id: str
        kind: str
        lane: str | None
        dataset_id: str | None
        seed: int | None
        input_json_path: Path
        runs: tuple[tuple[str, str, Path, str], ...]
        manifest_relative_path: str | None

    @dataclasses.dataclass(frozen=True, slots=True)
    class RunOverlay:
        """Plot-ready output from one source-finder run."""

        finder_id: str
        mode: str
        status: str
        wall_seconds: float | None
        source_count: int
        source_x: tuple[float, ...]
        source_y: tuple[float, ...]
        component_count: int
        component_x: tuple[float, ...]
        component_y: tuple[float, ...]
        significance_plane: npt.NDArray[np.float64] | None
        background_plane: npt.NDArray[np.float64] | None
        rms_plane: npt.NDArray[np.float64] | None
        support_mask: npt.NDArray[np.bool_] | None
        label_plane: npt.NDArray[np.int32] | None
        label_count: int
        notes: str

    return (
        CampaignCase,
        CatalogueSource,
        DatasetRecord,
        Path,
        RunOverlay,
        WCS,
        compare_support_component,
        dataclasses,
        fits,
        json,
        load_aegean_catalogue,
        load_comparison_catalogue,
        load_dataset_manifest,
        load_external_input_bundle,
        load_external_run_result,
        load_fits_plane,
        load_pybdsf_catalogue,
        math,
        np,
        npt,
        plot_support_component_diagnostic,
        plt,
        rank_reference_support_disagreements,
        read_beam_geometry,
    )


@app.cell(hide_code=True)
def _(
    CampaignCase,
    CatalogueSource,
    DatasetRecord,
    Path,
    RunOverlay,
    WCS,
    dataclasses,
    fits,
    json,
    load_aegean_catalogue,
    load_comparison_catalogue,
    load_dataset_manifest,
    load_external_input_bundle,
    load_external_run_result,
    load_fits_plane,
    load_pybdsf_catalogue,
    math,
    np,
    npt,
    plt,
):
    def _read_json_object(path: Path) -> dict[str, object]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"expected a JSON object: {path}")
        return value

    def normalise_campaign_path(raw: str) -> Path:
        return Path(raw).expanduser().resolve()

    def _resolve_relative_path(root: Path, raw: object, *, role: str) -> Path:
        relative = Path(str(raw))
        if relative.is_absolute():
            raise ValueError(f"{role} path must be relative: {relative}")
        resolved_root = root.resolve()
        resolved = (resolved_root / relative).resolve()
        if not resolved.is_relative_to(resolved_root):
            raise ValueError(f"{role} path escapes its root: {relative}")
        return resolved

    def _safe_float(value: object) -> float | None:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return number if np.isfinite(number) else None

    def _case_with_run(
        grouped: dict[str, CampaignCase],
        case: CampaignCase,
        run: tuple[str, str, Path, str],
    ) -> None:
        existing = grouped.get(case.key)
        grouped[case.key] = (
            dataclasses.replace(case, runs=(run,))
            if existing is None
            else dataclasses.replace(existing, runs=(*existing.runs, run))
        )

    def _external_case_from_path(
        root: Path,
        result_path: Path,
        finder_id: str,
        mode: str,
        status: str,
    ) -> CampaignCase | None:
        relative = result_path.relative_to(root.resolve()).parts
        minimum_result_parts = 7
        if len(relative) < minimum_result_parts or relative[0] != "results":
            return None
        lane, dataset_id, seed_token = relative[1:4]
        try:
            seed = int(seed_token.removeprefix("seed-"))
        except ValueError:
            return None
        return CampaignCase(
            key=f"{lane}/{dataset_id}/{seed_token}",
            label=f"{lane} | {dataset_id} | seed {seed}",
            case_id=f"{dataset_id}-{seed_token}",
            kind="external",
            lane=lane,
            dataset_id=dataset_id,
            seed=seed,
            input_json_path=(
                root / "inputs" / lane / dataset_id / seed_token / "input.json"
            ),
            runs=((finder_id, mode, result_path, status),),
            manifest_relative_path=None,
        )

    def _collect_external_cases(
        root: Path,
        campaign: dict[str, object],
        request: dict[str, object],
    ) -> list[CampaignCase]:
        raw_inputs = request.get("inputs", ())
        input_by_id = {
            str(item["input_id"]): item
            for item in raw_inputs
            if isinstance(item, dict) and "input_id" in item
        }
        grouped: dict[str, CampaignCase] = {}
        raw_runs = campaign.get("runs", ())
        if isinstance(raw_runs, list) and raw_runs:
            for item in raw_runs:
                if not isinstance(item, dict):
                    continue
                input_id = str(item.get("input_id", ""))
                input_record = input_by_id.get(input_id)
                if input_record is None:
                    continue
                lane = str(input_record.get("lane", ""))
                dataset_id = str(input_record.get("dataset_identifier", ""))
                seed_value = input_record.get("seed")
                if (
                    not lane
                    or not dataset_id
                    or not isinstance(seed_value, int)
                ):
                    continue
                seed_token = f"seed-{seed_value}"
                result_path = _resolve_relative_path(
                    root,
                    item.get("result_relative_path", ""),
                    role="campaign result",
                )
                finder_id = str(item.get("finder_id", "unknown"))
                mode = str(item.get("mode", "unknown"))
                status = str(item.get("status", "unknown"))
                relative_input = input_record.get(
                    "relative_directory",
                    f"inputs/{lane}/{dataset_id}/{seed_token}",
                )
                case = CampaignCase(
                    key=f"{lane}/{dataset_id}/{seed_token}",
                    label=f"{lane} | {dataset_id} | seed {seed_value}",
                    case_id=f"{dataset_id}-{seed_token}",
                    kind="external",
                    lane=lane,
                    dataset_id=dataset_id,
                    seed=seed_value,
                    input_json_path=_resolve_relative_path(
                        root,
                        f"{relative_input}/input.json",
                        role="campaign input",
                    ),
                    runs=(),
                    manifest_relative_path=(
                        str(input_record["manifest_relative_path"])
                        if "manifest_relative_path" in input_record
                        else None
                    ),
                )
                _case_with_run(
                    grouped,
                    case,
                    (finder_id, mode, result_path, status),
                )
            return sorted(grouped.values(), key=lambda item: item.label)

        for result_path in sorted(root.glob("results/**/*/result.json")):
            result = load_external_run_result(
                result_path,
                verify_artifacts=False,
            )
            case = _external_case_from_path(
                root,
                result_path,
                str(result.finder_id),
                str(result.mode),
                str(result.status),
            )
            if case is not None:
                _case_with_run(
                    grouped,
                    dataclasses.replace(case, runs=()),
                    case.runs[0],
                )
        return sorted(grouped.values(), key=lambda item: item.label)

    def _collect_public_cases(
        root: Path,
        campaign: dict[str, object],
        repository_root: Path,
    ) -> list[CampaignCase]:
        grouped: dict[str, CampaignCase] = {}
        base_campaign_value = campaign.get("base_campaign_repository_path")
        if base_campaign_value is not None:
            base_campaign_path = _resolve_relative_path(
                repository_root,
                base_campaign_value,
                role="base public campaign",
            )
            base_campaign = _read_json_object(base_campaign_path)
            for case in _collect_public_cases(
                base_campaign_path.parent,
                base_campaign,
                repository_root,
            ):
                grouped[case.key] = case
        raw_results = campaign.get("results", ())
        if not isinstance(raw_results, list):
            return sorted(grouped.values(), key=lambda item: item.label)
        for item in raw_results:
            if not isinstance(item, dict) or "result_path" not in item:
                continue
            case_id = str(item.get("case_id", ""))
            if not case_id:
                continue
            result_path = _resolve_relative_path(
                root,
                item["result_path"],
                role="public result",
            )
            finder_id = str(item.get("finder_id", "hebog"))
            mode = str(item.get("mode", "operational"))
            existing = grouped.get(f"public/{case_id}")
            case = existing or CampaignCase(
                key=f"public/{case_id}",
                label=f"public | {case_id}",
                case_id=case_id,
                kind="public",
                lane=None,
                dataset_id=None,
                seed=None,
                input_json_path=root / "inputs" / case_id / "input.json",
                runs=(),
                manifest_relative_path=None,
            )
            _case_with_run(
                grouped,
                dataclasses.replace(case, runs=()),
                (
                    finder_id,
                    mode,
                    result_path,
                    str(item.get("status", "unknown")),
                ),
            )
        return sorted(grouped.values(), key=lambda item: item.label)

    def _has_local_input(case: CampaignCase) -> bool:
        if not case.input_json_path.is_file():
            return False
        if case.kind != "external":
            return True
        try:
            bundle = load_external_input_bundle(
                case.input_json_path,
                verify_artifacts=False,
            )
        except (OSError, TypeError, ValueError):
            return False
        image_artifact = next(
            (item for item in bundle.artifacts if item.role == "image"),
            None,
        )
        return (
            image_artifact is not None
            and (
                case.input_json_path.parent / image_artifact.relative_path
            ).is_file()
        )

    def load_campaign_cases(root: Path) -> tuple[str, list[CampaignCase]]:
        campaign_path = root / "campaign.json"
        if not campaign_path.is_file():
            return "missing", []
        campaign = _read_json_object(campaign_path)
        external_request = root / "campaign-request.json"
        public_request = root / "request.json"
        if external_request.is_file():
            request = _read_json_object(external_request)
            cases = _collect_external_cases(root, campaign, request)
            return (
                "external synthetic",
                [case for case in cases if _has_local_input(case)],
            )
        if public_request.is_file():
            repository_root = Path(__file__).resolve().parents[1]
            cases = _collect_public_cases(root, campaign, repository_root)
            return "public", [case for case in cases if _has_local_input(case)]
        return "unsupported", []

    def _resolve_input_image(
        repository_root: Path,
        campaign_root: Path,  # noqa: ARG001
        case: CampaignCase,
    ) -> Path:
        if not case.input_json_path.is_file():
            raise FileNotFoundError(
                f"missing input record: {case.input_json_path}"
            )
        if case.kind == "external":
            bundle = load_external_input_bundle(
                case.input_json_path,
                verify_artifacts=False,
            )
            image_artifact = next(
                item for item in bundle.artifacts if item.role == "image"
            )
            return _resolve_relative_path(
                case.input_json_path.parent,
                image_artifact.relative_path,
                role="external input image",
            )

        record = _read_json_object(case.input_json_path)
        location = str(record.get("input_location", ""))
        if "input_path" not in record:
            raise ValueError("public input record has no input_path")
        if location == "repository":
            return _resolve_relative_path(
                repository_root,
                record["input_path"],
                role="repository input",
            )
        if location == "staging":
            public_input_root = case.input_json_path.parents[2]
            return _resolve_relative_path(
                public_input_root,
                record["input_path"],
                role="staged input",
            )
        raise ValueError(f"unsupported public input_location: {location!r}")

    def _load_dataset_record(
        repository_root: Path,
        case: CampaignCase,
    ) -> DatasetRecord | None:
        if case.dataset_id is None or case.manifest_relative_path is None:
            return None
        manifest_path = _resolve_relative_path(
            repository_root,
            case.manifest_relative_path,
            role="dataset manifest",
        )
        if not manifest_path.is_file():
            return None
        manifest = load_dataset_manifest(manifest_path)
        return next(
            (
                dataset
                for dataset in manifest.datasets
                if dataset.identifier == case.dataset_id
            ),
            None,
        )

    def _load_truth_points(
        dataset: DatasetRecord | None,
    ) -> dict[str, tuple[tuple[float, float], ...]]:
        if dataset is None:
            return {}
        output = {
            "all-injected": tuple(
                (source.x_pixel, source.y_pixel)
                for source in dataset.recipe.sources
            )
        }
        for stratum in dataset.validation_strata:
            output[f"validation: {stratum.identifier}"] = tuple(
                (
                    dataset.recipe.sources[index].x_pixel,
                    dataset.recipe.sources[index].y_pixel,
                )
                for index in stratum.source_indices
            )
        for stratum in dataset.classification_strata:
            output[f"class: {stratum.identifier}"] = tuple(
                (
                    dataset.recipe.sources[index].x_pixel,
                    dataset.recipe.sources[index].y_pixel,
                )
                for index in stratum.source_indices
            )
        return output

    def _catalogue_for_finder(
        finder_id: str,
        role_map: dict[str, Path],
    ) -> tuple[CatalogueSource, ...]:
        comparison_path = role_map.get("comparison-catalogue-json")
        if comparison_path is not None:
            return load_comparison_catalogue(comparison_path)
        if finder_id == "hebog":
            path = (
                role_map.get("source-catalogue-json")
                or role_map.get("segment-catalogue-json")
                or role_map.get("compact-catalogue-json")
            )
            return load_comparison_catalogue(path) if path is not None else ()
        if finder_id in {"released-pybdsf", "pinned-pybdsf-master"}:
            path = role_map.get("source-catalogue-fits")
            return load_pybdsf_catalogue(path) if path is not None else ()
        if finder_id == "aegean":
            component_path = role_map.get("component-catalogue-fits")
            island_path = role_map.get("island-catalogue-fits")
            if component_path is not None and island_path is not None:
                return load_aegean_catalogue(component_path, island_path)
        return ()

    def _label_role_for_finder(finder_id: str) -> str | None:
        return {
            "hebog": "segment-labels-fits",
            "released-pybdsf": "island-labels-fits",
            "pinned-pybdsf-master": "island-labels-fits",
            "aegean": "support-proxy-labels-fits",
        }.get(finder_id)

    def _to_pixel_positions(
        wcs: WCS,
        sources: tuple[CatalogueSource, ...],
    ) -> tuple[tuple[float, ...], tuple[float, ...]]:
        if not sources:
            return (), ()
        world = np.asarray(
            [
                (
                    source.right_ascension_degrees,
                    source.declination_degrees,
                )
                for source in sources
            ],
            dtype=np.float64,
        )
        pixels = wcs.all_world2pix(world, 0)
        finite = np.all(np.isfinite(pixels), axis=1)
        return (
            tuple(float(value) for value in pixels[finite, 0]),
            tuple(float(value) for value in pixels[finite, 1]),
        )

    def _public_core_bounds(
        result: dict[str, object],
        shape_yx: tuple[int, int],
    ) -> tuple[int, int, int, int] | None:
        raw = result.get("core_bounds_yx_half_open")
        core_bound_count = 4
        if not isinstance(raw, list) or len(raw) != core_bound_count:
            return None
        if not all(isinstance(value, int) for value in raw):
            return None
        y_start, y_stop, x_start, x_stop = raw
        if not (
            0 <= y_start < y_stop <= shape_yx[0]
            and 0 <= x_start < x_stop <= shape_yx[1]
        ):
            return None
        return y_start, y_stop, x_start, x_stop

    def _artifact_role_map(
        result_path: Path,
        artifacts: object,
    ) -> dict[str, Path]:
        if not isinstance(artifacts, dict):
            return {}
        role_map: dict[str, Path] = {}
        for role, payload in artifacts.items():
            if isinstance(payload, dict) and "path" in payload:
                role_map[str(role)] = _resolve_relative_path(
                    result_path.parent,
                    payload["path"],
                    role=f"{role} artifact",
                )
        return role_map

    def _failed_overlay(
        finder_id: str,
        mode: str,
        status: str,
        wall_seconds: float | None,
        notes: str,
    ) -> RunOverlay:
        return RunOverlay(
            finder_id=finder_id,
            mode=mode,
            status=status,
            wall_seconds=wall_seconds,
            source_count=0,
            source_x=(),
            source_y=(),
            component_count=0,
            component_x=(),
            component_y=(),
            significance_plane=None,
            background_plane=None,
            rms_plane=None,
            support_mask=None,
            label_plane=None,
            label_count=0,
            notes=notes,
        )

    def load_case_overlays(  # noqa: PLR0912
        case: CampaignCase,
        repository_root: Path,
        campaign_root: Path,
    ) -> tuple[
        npt.NDArray[np.float64],
        Path,
        dict[str, RunOverlay],
        dict[str, tuple[tuple[float, float], ...]],
        list[str],
    ]:
        image_path = _resolve_input_image(repository_root, campaign_root, case)
        if not image_path.is_file():
            raise FileNotFoundError(
                f"input image does not exist: {image_path}"
            )
        image = load_fits_plane(image_path)
        wcs = WCS(fits.getheader(image_path), relax=True).celestial
        warnings: list[str] = []

        if case.kind == "public" and case.runs:
            public_result_path = case.runs[0][2]
            if public_result_path.is_file():
                public_result = _read_json_object(public_result_path)
                bounds = _public_core_bounds(public_result, image.shape)
                if bounds is not None:
                    y_start, y_stop, x_start, x_stop = bounds
                    image = image[y_start:y_stop, x_start:x_stop]
                    wcs = wcs.slice(
                        (slice(y_start, y_stop), slice(x_start, x_stop))
                    )
                elif "core_bounds_yx_half_open" in public_result:
                    warnings.append("public result has invalid core bounds")

        dataset = (
            _load_dataset_record(repository_root, case)
            if case.kind == "external"
            else None
        )
        truth = _load_truth_points(dataset)
        overlays: dict[str, RunOverlay] = {}

        for (
            recorded_finder,
            recorded_mode,
            result_path,
            recorded_status,
        ) in case.runs:
            key = f"{recorded_finder}/{recorded_mode}"
            if not result_path.is_file():
                warnings.append(f"missing result: {result_path}")
                overlays[key] = _failed_overlay(
                    recorded_finder,
                    recorded_mode,
                    recorded_status,
                    None,
                    "result file is missing",
                )
                continue

            if case.kind == "external":
                result = load_external_run_result(
                    result_path,
                    verify_artifacts=False,
                )
                finder_id = str(result.finder_id)
                mode = str(result.mode)
                status = str(result.status)
                wall_seconds = _safe_float(result.wall_seconds)
                role_map = {
                    item.role: _resolve_relative_path(
                        result_path.parent,
                        item.relative_path,
                        role=f"{item.role} artifact",
                    )
                    for item in result.artifacts
                }
            else:
                result = _read_json_object(result_path)
                finder_id = recorded_finder
                mode = recorded_mode
                status = str(result.get("status", recorded_status))
                wall_seconds = _safe_float(result.get("elapsed_seconds"))
                role_map = _artifact_role_map(
                    result_path,
                    result.get("artifacts", {}),
                )

            key = f"{finder_id}/{mode}"
            if status != "success":
                overlays[key] = _failed_overlay(
                    finder_id,
                    mode,
                    status,
                    wall_seconds,
                    "run did not succeed",
                )
                continue

            notes: list[str] = []
            try:
                catalogue = _catalogue_for_finder(finder_id, role_map)
            except (KeyError, OSError, TypeError, ValueError) as error:
                catalogue = ()
                notes.append(f"catalogue load failed: {error}")
            if not catalogue:
                notes.append("no catalogue rows or catalogue artifact")
            source_catalogue = catalogue
            component_catalogue: tuple[CatalogueSource, ...] = ()
            if finder_id == "hebog" and "source-catalogue-json" in role_map:
                source_path = role_map["source-catalogue-json"]
                component_path = role_map.get("component-catalogue-json")
                try:
                    source_catalogue = load_comparison_catalogue(source_path)
                    component_catalogue = (
                        load_comparison_catalogue(component_path)
                        if component_path is not None
                        else ()
                    )
                    notes.append(
                        f"{len(source_catalogue)} associated sources from "
                        f"{len(component_catalogue)} Gaussian components"
                    )
                except (KeyError, OSError, TypeError, ValueError) as error:
                    notes.append(f"Hebog catalogue load failed: {error}")

            try:
                source_x, source_y = _to_pixel_positions(wcs, source_catalogue)
                component_x, component_y = _to_pixel_positions(
                    wcs, component_catalogue
                )
            except (TypeError, ValueError) as error:
                source_x, source_y = (), ()
                component_x, component_y = (), ()
                notes.append(f"WCS conversion failed: {error}")

            label_plane = None
            label_count = 0
            significance_plane = None
            background_plane = None
            rms_plane = None
            support_mask = None
            label_role = _label_role_for_finder(finder_id)
            label_path = (
                role_map.get(label_role) if label_role is not None else None
            )
            if label_path is None:
                notes.append("no label artifact")
            else:
                try:
                    raw_labels = load_fits_plane(label_path)
                    if raw_labels.shape != image.shape:
                        notes.append(
                            "label shape "
                            f"{raw_labels.shape} != image {image.shape}"
                        )
                    else:
                        label_plane = np.asarray(raw_labels, dtype=np.int32)
                        label_count = int(
                            np.count_nonzero(np.unique(label_plane) > 0)
                        )
                except (OSError, TypeError, ValueError) as error:
                    notes.append(f"label load failed: {error}")

            if finder_id == "hebog":
                mask_path = role_map.get("segment-mask-fits")
                if mask_path is None:
                    notes.append("no Rapthor source-filtering mask artifact")
                else:
                    try:
                        raw_mask = load_fits_plane(mask_path)
                        if raw_mask.shape != image.shape:
                            notes.append(
                                "source-filtering mask shape "
                                f"{raw_mask.shape} != image {image.shape}"
                            )
                        else:
                            support_mask = np.asarray(
                                raw_mask > 0, dtype=np.bool_
                            )
                    except (OSError, TypeError, ValueError) as error:
                        notes.append(
                            f"source-filtering mask load failed: {error}"
                        )
                background_path = role_map.get("background-fits")
                rms_path = role_map.get("rms-fits")
                if background_path is None or rms_path is None:
                    notes.append(
                        "no background/RMS artifacts for significance"
                    )
                else:
                    try:
                        background = load_fits_plane(background_path)
                        rms = load_fits_plane(rms_path)
                        if background.shape != image.shape:
                            notes.append(
                                "background shape "
                                f"{background.shape} != image {image.shape}"
                            )
                        elif rms.shape != image.shape:
                            notes.append(
                                f"RMS shape {rms.shape} != image {image.shape}"
                            )
                        else:
                            background_plane = background
                            rms_plane = rms
                            valid_significance = (
                                np.isfinite(image)
                                & np.isfinite(background)
                                & np.isfinite(rms)
                                & (rms > 0)
                            )
                            significance_plane = np.full_like(
                                image,
                                np.nan,
                                dtype=np.float64,
                            )
                            np.divide(
                                image - background,
                                rms,
                                out=significance_plane,
                                where=valid_significance,
                            )
                    except (OSError, TypeError, ValueError) as error:
                        notes.append(f"significance load failed: {error}")
            elif label_plane is not None:
                support_mask = np.asarray(label_plane > 0, dtype=np.bool_)

            overlays[key] = RunOverlay(
                finder_id=finder_id,
                mode=mode,
                status=status,
                wall_seconds=wall_seconds,
                source_count=len(source_catalogue),
                source_x=source_x,
                source_y=source_y,
                component_count=len(component_catalogue),
                component_x=component_x,
                component_y=component_y,
                significance_plane=significance_plane,
                background_plane=background_plane,
                rms_plane=rms_plane,
                support_mask=support_mask,
                label_plane=label_plane,
                label_count=label_count,
                notes="; ".join(notes),
            )

        return image, image_path, overlays, truth, warnings

    def _markdown_cell(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    def _finder_order(overlay: RunOverlay) -> tuple[int, str]:
        order = {
            "hebog": 0,
            "released-pybdsf": 1,
            "pinned-pybdsf-master": 2,
            "aegean": 3,
        }
        return order.get(overlay.finder_id, 99), overlay.mode

    def format_overlay_summary(overlays: dict[str, RunOverlay]) -> str:
        lines = [
            "| Finder | Mode | Status | Sources/catalogue rows | "
            "Gaussian components | Support labels | "
            "Recorded wall time (s) | Notes |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
        for overlay in sorted(overlays.values(), key=_finder_order):
            wall = (
                f"{overlay.wall_seconds:.3f}"
                if overlay.wall_seconds is not None
                else "unavailable"
            )
            lines.append(
                "| "
                + " | ".join(
                    (
                        _markdown_cell(overlay.finder_id),
                        _markdown_cell(overlay.mode),
                        _markdown_cell(overlay.status),
                        str(overlay.source_count),
                        (
                            str(overlay.component_count)
                            if overlay.finder_id == "hebog"
                            else "n/a"
                        ),
                        str(overlay.label_count),
                        wall,
                        _markdown_cell(overlay.notes or "none"),
                    )
                )
                + " |"
            )
        return "\n".join(lines)

    def _image_limits(image: npt.NDArray[np.float64]) -> tuple[float, float]:
        finite = image[np.isfinite(image)]
        if finite.size == 0:
            return 0.0, 1.0
        minimum, maximum = np.percentile(finite, (2.0, 99.5))
        if minimum == maximum:
            padding = max(abs(float(minimum)) * 0.05, 1.0)
            return float(minimum - padding), float(maximum + padding)
        return float(minimum), float(maximum)

    def plot_case(
        case: CampaignCase,
        image: npt.NDArray[np.float64],
        overlays: dict[str, RunOverlay],
        truth_label: str | None,
        truth_points: tuple[tuple[float, float], ...],
    ) -> plt.Figure:
        successful = sorted(
            (item for item in overlays.values() if item.status == "success"),
            key=_finder_order,
        )
        significance_overlay = next(
            (
                overlay
                for overlay in successful
                if overlay.finder_id == "hebog"
                and overlay.significance_plane is not None
            ),
            None,
        )
        panel_count = (
            1 + len(successful) + int(significance_overlay is not None)
        )
        column_count = 1 if panel_count == 1 else 2
        row_count = math.ceil(panel_count / column_count)
        figure, axes = plt.subplots(
            row_count,
            column_count,
            figsize=(7.0 * column_count, 5.5 * row_count),
            sharex=True,
            sharey=True,
            squeeze=False,
        )
        flat_axes = list(axes.flat)
        minimum, maximum = _image_limits(image)

        def draw_image(axis) -> None:
            axis.imshow(
                image,
                origin="lower",
                cmap="gray",
                vmin=minimum,
                vmax=maximum,
                interpolation="nearest",
            )
            axis.set(xlabel="x pixel", ylabel="y pixel")
            if truth_points:
                x_values = [point[0] for point in truth_points]
                y_values = [point[1] for point in truth_points]
                axis.scatter(
                    x_values,
                    y_values,
                    s=46,
                    marker="*",
                    facecolors="gold",
                    edgecolors="black",
                    linewidths=0.7,
                    label=f"Truth: {truth_label}",
                    zorder=4,
                )

        input_axis = flat_axes[0]
        draw_image(input_axis)
        input_axis.set_title(
            "Input image"
            + (
                f" | {len(truth_points)} known sources in selected truth layer"
                if truth_points
                else ""
            )
        )
        if truth_points:
            input_axis.legend(loc="best", fontsize="small")

        overlay_axis_start = 1
        if significance_overlay is not None:
            significance_axis = flat_axes[1]
            significance_image = significance_axis.imshow(
                significance_overlay.significance_plane,
                origin="lower",
                cmap="RdBu_r",
                vmin=-8.0,
                vmax=8.0,
                interpolation="nearest",
            )
            significance_axis.set(xlabel="x pixel", ylabel="y pixel")
            if significance_overlay.support_mask is not None:
                significance_axis.contour(
                    significance_overlay.support_mask,
                    levels=[0.5],
                    colors=["black"],
                    linewidths=0.8,
                    alpha=0.9,
                )
            significance_axis.set_title(
                "Hebog local significance (-8 to +8 sigma)\n"
                "(input - background) / RMS; black = support mask"
            )
            figure.colorbar(
                significance_image,
                ax=significance_axis,
                fraction=0.046,
                pad=0.04,
                label="Local significance (sigma)",
            )
            overlay_axis_start = 2

        colours = plt.rcParams["axes.prop_cycle"].by_key().get("color", ["C0"])
        markers = {
            "hebog": "o",
            "released-pybdsf": "s",
            "pinned-pybdsf-master": "^",
            "aegean": "D",
        }
        for index, overlay in enumerate(
            successful,
            start=overlay_axis_start,
        ):
            axis = flat_axes[index]
            draw_image(axis)
            colour = colours[(index - overlay_axis_start) % len(colours)]
            if overlay.finder_id == "hebog" and overlay.component_x:
                axis.scatter(
                    overlay.component_x,
                    overlay.component_y,
                    s=30,
                    marker="o",
                    facecolors="none",
                    edgecolors=colour,
                    linewidths=1.2,
                    label="Hebog Gaussian components",
                    zorder=5,
                )
            if overlay.finder_id == "hebog" and overlay.source_x:
                axis.scatter(
                    overlay.source_x,
                    overlay.source_y,
                    s=38,
                    marker="x",
                    color=colour,
                    linewidths=1.2,
                    label="Hebog associated sources",
                    zorder=6,
                )
            elif overlay.source_x:
                axis.scatter(
                    overlay.source_x,
                    overlay.source_y,
                    s=38,
                    marker=markers.get(overlay.finder_id, "o"),
                    facecolors="none",
                    edgecolors=colour,
                    linewidths=1.2,
                    label=f"{overlay.finder_id} catalogue",
                    zorder=6,
                )
            if overlay.support_mask is not None and np.any(
                overlay.support_mask
            ):
                support = np.asarray(overlay.support_mask, dtype=np.bool_)
                axis.contourf(
                    support,
                    levels=[0.5, 1.5],
                    colors=[colour],
                    alpha=0.18,
                    antialiased=False,
                    zorder=3,
                )
                if overlay.label_plane is not None:
                    label_plane = np.asarray(overlay.label_plane)
                    label_boundaries = np.zeros_like(support)
                    horizontal_changes = (
                        label_plane[:, 1:] != label_plane[:, :-1]
                    )
                    vertical_changes = (
                        label_plane[1:, :] != label_plane[:-1, :]
                    )
                    label_boundaries[:, 1:] |= horizontal_changes
                    label_boundaries[:, :-1] |= horizontal_changes
                    label_boundaries[1:, :] |= vertical_changes
                    label_boundaries[:-1, :] |= vertical_changes
                    label_boundaries &= support
                    axis.contourf(
                        label_boundaries,
                        levels=[0.5, 1.5],
                        colors=[colour],
                        alpha=0.72,
                        antialiased=False,
                        zorder=4,
                    )
            count_summary = (
                f"{overlay.source_count} associated sources | "
                f"{overlay.component_count} Gaussian components | "
                f"{overlay.label_count} support labels"
                if overlay.finder_id == "hebog"
                else f"{overlay.source_count} catalogue rows | "
                f"{overlay.label_count} support labels"
            )
            axis.set_title(
                f"{overlay.finder_id} | {overlay.mode}\n{count_summary}"
            )
            if overlay.source_x or overlay.component_x:
                axis.legend(loc="best", fontsize="small")

        for axis in flat_axes[panel_count:]:
            axis.set_visible(False)
        figure.suptitle(case.label)
        figure.tight_layout()
        return figure

    return (
        format_overlay_summary,
        load_campaign_cases,
        load_case_overlays,
        normalise_campaign_path,
        plot_case,
    )


@app.cell(hide_code=True)
def _(Path, mo):
    repository_root = Path(__file__).resolve().parents[1]
    campaign_root = mo.ui.text(
        label="Campaign root",
        value=str(
            repository_root
            / "benchmark-results"
            / "phase-5"
            / "hebog-notebook-refreshes"
            / "latest"
        ),
        placeholder="/path/to/sealed/campaign",
        full_width=True,
    )
    include_failed_runs = mo.ui.switch(
        value=True,
        label="Include failed runs in the summary",
    )
    mo.vstack(
        [
            mo.md(r"""
            # Campaign source-finder comparison

            Inspect one sealed validation campaign case at a time. External
            synthetic campaigns compare Hebog, released PyBDSF, pinned PyBDSF
            master, and Aegean against injected truth. Public campaigns expose
            the Hebog result over the governed public image; their reference
            catalogue comparisons remain in the compiled campaign evidence.
            """),
            campaign_root,
            include_failed_runs,
        ]
    )
    return campaign_root, include_failed_runs, repository_root


@app.cell(hide_code=True)
def _(campaign_root, load_campaign_cases, mo, normalise_campaign_path):
    root = normalise_campaign_path(campaign_root.value)
    campaign_error = None
    try:
        campaign_kind, cases = load_campaign_cases(root)
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        campaign_kind, cases = "invalid", []
        campaign_error = str(error)

    if cases:
        case_options = {case.label: case.key for case in cases}
        preferred_case_key = "public/sdc1-ordinary-y06-x09"
        first_label = next(
            (
                label
                for label, key in case_options.items()
                if key == preferred_case_key
            ),
            next(iter(case_options)),
        )
        case_selector = mo.ui.dropdown(
            options=case_options,
            value=first_label,
            searchable=True,
            label=f"Case | {len(cases)} available",
            full_width=True,
        )
    else:
        message = {
            "missing": "No campaign.json was found.",
            "unsupported": "The directory is not a supported campaign layout.",
            "invalid": f"Campaign could not be read: {campaign_error}",
        }.get(campaign_kind, "The campaign contains no cases.")
        case_selector = mo.ui.dropdown(
            options={message: None},
            value=message,
            label="Case",
            disabled=True,
            full_width=True,
        )

    mo.vstack(
        [
            mo.md(f"**Detected campaign:** {campaign_kind}  \n`{root}`"),
            case_selector,
        ]
    )
    return case_selector, cases, root


@app.cell(hide_code=True)
def _(
    CampaignCase,
    case_selector,
    cases,
    load_case_overlays,
    mo,
    repository_root,
    root,
):
    selected_key = case_selector.value
    selected_case: CampaignCase | None = next(
        (case for case in cases if case.key == selected_key),
        None,
    )
    mo.stop(
        selected_case is None,
        mo.callout("Select a valid campaign case to continue.", kind="warn"),
    )

    load_error = None
    try:
        image, image_path, overlays, truth, warnings = load_case_overlays(
            selected_case,
            repository_root,
            root,
        )
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        load_error = str(error)
        image = image_path = overlays = truth = warnings = None
    mo.stop(
        load_error is not None,
        mo.callout(
            f"The selected case could not be loaded: {load_error}",
            kind="danger",
        ),
    )
    return image, image_path, overlays, selected_case, truth, warnings


@app.cell(hide_code=True)
def _(mo, truth):
    if truth:
        truth_options = {
            "All injected sources": "all-injected",
            **{label: label for label in truth if label != "all-injected"},
            "Hide injected truth": None,
        }
        truth_selector = mo.ui.dropdown(
            options=truth_options,
            value="All injected sources",
            label="Synthetic truth layer",
            full_width=True,
        )
    else:
        unavailable_label = "No injected truth is available for this case"
        truth_selector = mo.ui.dropdown(
            options={unavailable_label: None},
            value=unavailable_label,
            label="Synthetic truth layer",
            disabled=True,
            full_width=True,
        )
    mo.vstack([truth_selector])
    return (truth_selector,)


@app.cell(hide_code=True)
def _(
    format_overlay_summary,
    image,
    image_path,
    include_failed_runs,
    mo,
    overlays,
    plot_case,
    selected_case,
    truth,
    truth_selector,
    warnings,
):
    selected_truth = truth_selector.value
    truth_points = (
        truth.get(selected_truth, ()) if selected_truth is not None else ()
    )
    figure = plot_case(
        selected_case,
        image,
        overlays,
        selected_truth,
        truth_points,
    )
    interactive_figure = mo.mpl.interactive(figure)
    summary_overlays = (
        overlays
        if include_failed_runs.value
        else {
            key: overlay
            for key, overlay in overlays.items()
            if overlay.status == "success"
        }
    )
    warning_output = (
        mo.callout(
            "\n".join(f"- {warning}" for warning in warnings),
            kind="warn",
        )
        if warnings
        else mo.md("")
    )
    mo.vstack(
        [
            mo.md(f"## {selected_case.label}\n\nInput image: `{image_path}`"),
            warning_output,
            mo.md(
                "Use the plot controls to zoom or pan. The subplot axes are "
                "linked, so every view keeps the same pixel bounds. "
                "For Hebog, translucent colour is loaded directly from its "
                "Rapthor source-filtering mask; darker edges come from the "
                "segment labels."
            ),
            interactive_figure,
            mo.md("## Run evidence"),
            mo.md(format_overlay_summary(summary_overlays)),
            mo.md(
                """
    ### Evidence-table columns

    | Column | Definition |
    | --- | --- |
    | **Finder** | Source-finding program that produced the result. |
    | **Mode** | Governed configuration used for that finder; modes are defined below. |
    | **Status** | Whether the recorded run completed successfully. A failed run can retain diagnostic metadata but is not scientific evidence. |
    | **Catalogue rows** | Measurement records emitted by the finder. A row is not necessarily one distinct astrophysical source, and this count can differ from the support-label count. |
    | **Support labels** | Distinct positive regions in the displayed support map: Hebog segments, PyBDSF islands, or Aegean support proxies. |
    | **Recorded wall time (s)** | Elapsed real time stored for that run, in seconds. This is context, not by itself evidence of a speedup across finders, modes, or machines. |
    | **Notes** | Missing, empty, invalid, or display-conversion issues. `none` means no issue was recorded; `unavailable` means no value was provided. |

    ### Finder and mode names

    | Term | Definition |
    | --- | --- |
    | **Hebog** | Candidate source finder being scientifically validated. |
    | **Released PyBDSF** | Released PyBDSF version used by Rapthor as the production comparison baseline. |
    | **Pinned PyBDSF master** | Separately pinned PyBDSF development revision used as a second comparison baseline. |
    | **Aegean** | Aegean source finder used as an independent public comparison. |
    | **Candidate** | Governed Hebog configuration under validation. |
    | **Operational** | A finder's governed normal configuration, including its usual background and noise-estimation path. |
    | **Controlled background** | A reference finder receives the same supplied analytic background and RMS noise planes. This separates source extraction from background estimation. |

    ### Plot vocabulary

    | Term | Definition |
    | --- | --- |
    | **Input image** | Selected FITS brightness plane. For a public case, the notebook uses the governed comparison region when the result declares crop bounds. |
    | **Catalogue marker** | Catalogue position transformed through the FITS world-coordinate system into zero-based image-pixel coordinates. |
    | **Support mask** | Translucent overlay covering every positive pixel assigned to a finder. Hebog's overlay is loaded directly from the campaign's `segment-mask-fits`, the retained Boolean support product for source filtering in this validation profile. It is not an uncertainty region. |
    | **Support-label boundary** | Darker edge wherever neighbouring support-label IDs differ, including the edge between labelled and unlabelled pixels. |
    | **Segment** | Hebog's accepted connected support region. A segment can exist without a measurable catalogue row. |
    | **Island** | PyBDSF's native connected support region. An island can contain more than one fitted catalogue component. |
    | **Aegean support proxy** | Ellipse-derived comparison region constructed from Aegean catalogue components and island identifiers. It is not a native Aegean pixel-segmentation map. |
    | **Injected truth** | Known simulated emitters created before any finder is run. This is authoritative truth for synthetic campaigns. |
    | **Truth layer** | Selected truth subset drawn over a synthetic image. Public observations do not have injected truth. |
    | **Validation stratum** | Predeclared diagnostic subset, such as an SNR or image-edge band. Validation strata may overlap. |
    | **Classification stratum** | Predeclared, disjoint source-type population, such as compact, blended, or extended sources. |
    | **FITS** | Flexible Image Transport System, the astronomy image and metadata format used here. |
    | **WCS** | World Coordinate System metadata that maps image pixels to sky coordinates. |
    | **RMS** | Root-mean-square noise level used to express detection significance. |
    | **Local significance** | Background-subtracted brightness divided by Hebog's recorded local RMS: `(input - background) / RMS`. The colour scale is clipped at -8 and +8 sigma for display only; this does not change the mask. |

    ### Validation terms

    | Term | Definition |
    | --- | --- |
    | **Completeness** | Fraction of eligible truth sources recovered by the finder. |
    | **Reliability** | Fraction of reported detections associated with eligible truth. |
    | **Astrometry** | Accuracy of the reported sky position. |
    | **Photometry** | Accuracy of measured source flux. |
    | **Shape** | Accuracy of fitted or deconvolved source size and orientation. |
    | **Association** | Governed matching of catalogue components or support regions to the same truth object. Finders are matched independently to truth, not voted against one another. |
    | **Non-inferiority** | Statistical test that Hebog is not worse than a reference by more than a predeclared scientifically acceptable margin. |
    | **Governed** | Defined by the validation protocol before interpreting the result, rather than chosen after seeing the outcome. |
    | **Sealed campaign** | Completed campaign whose manifest and evidence are treated as immutable validation records. |

    Counts and visual agreement are useful diagnostics, but do not establish
    scientific equivalence alone. Public data has no injected truth, so finder
    agreement there is descriptive rather than ground truth.
                    """
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo, overlays):
    support_candidate_overlay = next(
        (
            overlay
            for overlay in overlays.values()
            if overlay.finder_id == "hebog"
            and overlay.mode == "operational"
            and overlay.status == "success"
            and overlay.label_plane is not None
            and overlay.background_plane is not None
            and overlay.rms_plane is not None
        ),
        None,
    )
    mo.stop(
        support_candidate_overlay is None,
        mo.callout(
            "Component diagnostics require successful Hebog labels, "
            "background, and RMS products.",
            kind="warn",
        ),
    )
    _reference_options = {
        f"{overlay.finder_id} | {overlay.mode}": key
        for key, overlay in overlays.items()
        if overlay.finder_id != "hebog"
        and overlay.status == "success"
        and overlay.label_plane is not None
    }
    mo.stop(
        not _reference_options,
        mo.callout(
            "Component diagnostics require another finder's label plane. "
            "They are unavailable for Hebog-only campaigns.",
            kind="warn",
        ),
    )
    _preferred_reference_label = next(
        (
            label
            for label in _reference_options
            if label.startswith("released-pybdsf |")
        ),
        next(iter(_reference_options)),
    )
    support_reference_selector = mo.ui.dropdown(
        options=_reference_options,
        value=_preferred_reference_label,
        label="Comparison label plane",
        full_width=True,
    )
    mo.vstack(
        [
            mo.md("## Diagnose one support component"),
            mo.md(
                "Ranked components put fragmentation first, then the number "
                "of comparison-only pixels. This is triage—not a declaration "
                "that the comparison finder is ground truth."
            ),
            support_reference_selector,
        ]
    )
    return support_candidate_overlay, support_reference_selector


@app.cell(hide_code=True)
def _(
    mo,
    overlays,
    rank_reference_support_disagreements,
    support_candidate_overlay,
    support_reference_selector,
):
    support_reference_overlay = overlays[support_reference_selector.value]
    _ranked_components = rank_reference_support_disagreements(
        support_candidate_overlay.label_plane,
        support_reference_overlay.label_plane,
    )
    _disagreements = tuple(
        item
        for item in _ranked_components
        if item.reference_only_pixel_count > 0
        or item.candidate_only_pixel_count > 0
        or item.fragment_count != 1
    )
    _triaged_components = (_disagreements or _ranked_components)[:100]
    _component_options = {
        (
            f"label {item.reference_label} | {item.fragment_count} Hebog "
            f"fragments | {item.reference_only_pixel_count:,} "
            f"comparison-only px | recall {item.recall:.3f}"
        ): item.reference_label
        for item in _triaged_components
    }
    mo.stop(
        not _component_options,
        mo.callout("The comparison label plane is empty.", kind="warn"),
    )
    _first_component_label = next(iter(_component_options))
    support_component_selector = mo.ui.dropdown(
        options=_component_options,
        value=_first_component_label,
        searchable=True,
        label=(
            f"Support component | top {len(_component_options)} "
            "diagnostic disagreements"
        ),
        full_width=True,
    )
    mo.vstack([support_component_selector])
    return support_component_selector, support_reference_overlay


@app.cell(hide_code=True)
def _(
    compare_support_component,
    image,
    image_path,
    mo,
    plot_support_component_diagnostic,
    read_beam_geometry,
    support_candidate_overlay,
    support_component_selector,
    support_reference_overlay,
):
    _comparison = compare_support_component(
        support_candidate_overlay.label_plane,
        support_reference_overlay.label_plane,
        support_component_selector.value,
    )
    _beam_area_pixels, _beam_width_pixels = read_beam_geometry(
        image_path,
        None,
    )
    _reference_name = support_reference_overlay.finder_id
    _diagnostic_figure, _ = plot_support_component_diagnostic(
        image=image,
        background=support_candidate_overlay.background_plane,
        rms=support_candidate_overlay.rms_plane,
        candidate_labels=support_candidate_overlay.label_plane,
        reference_labels=support_reference_overlay.label_plane,
        comparison=_comparison,
        beam_area_pixels=_beam_area_pixels,
        beam_width_pixels=_beam_width_pixels,
        padding_beams=3.0,
        candidate_name="Hebog",
        reference_name=_reference_name,
    )
    mo.vstack(
        [
            mo.md(
                "Orange-only pixels are not automatically missed true "
                "emission. Judge them using the image, Hebog background/RMS, "
                "direct significance, S/N distributions, and flux accounting."
            ),
            mo.mpl.interactive(_diagnostic_figure),
        ]
    )
    return


@app.cell(hide_code=True)
def _(Path, cases, json, mo, repository_root):
    _history_index_path = (
        repository_root
        / "benchmark-results"
        / "phase-5"
        / "hebog-notebook-refreshes"
        / "index.json"
    )
    history_records: tuple[dict[str, object], ...] = ()
    _history_error = None
    try:
        _history_document = json.loads(
            _history_index_path.read_text(encoding="utf-8")
        )
        _raw_history = _history_document.get("refreshes", ())
        if not isinstance(_raw_history, list):
            raise ValueError("history refreshes must be a list")
        history_records = tuple(
            _item for _item in _raw_history if isinstance(_item, dict)
        )
    except (OSError, TypeError, ValueError) as _history_load_error:
        _history_error = str(_history_load_error)

    _history_options: dict[str, str] = {}
    for _registered_run in history_records:
        _campaign_path = str(
            _registered_run.get("campaign_repository_path", "")
        )
        if not _campaign_path:
            continue
        _display_label = (
            f"{_registered_run.get('label', Path(_campaign_path).name)} | "
            f"{str(_registered_run.get('source_tree_sha256') or 'unknown')[:8]} | "
            f"{_registered_run.get('case_count', '?')} cases"
        )
        _history_options[_display_label] = _campaign_path
    _default_history_labels = list(_history_options)[-3:]
    history_selector = mo.ui.multiselect(
        options=_history_options,
        value=_default_history_labels,
        label="Hebog runs to compare",
        full_width=True,
    )
    _history_dataset_options = {_case.label: _case.case_id for _case in cases}
    _preferred_history_case_id = "sdc1-ordinary-y06-x09"
    _default_history_dataset_label = next(
        (
            _label
            for _label, _case_id in _history_dataset_options.items()
            if _case_id == _preferred_history_case_id
        ),
        next(iter(_history_dataset_options), None),
    )
    history_dataset_selector = mo.ui.dropdown(
        options=_history_dataset_options,
        value=_default_history_dataset_label,
        searchable=True,
        label=f"Dataset | {len(_history_dataset_options)} available",
        full_width=True,
    )
    _history_status = (
        mo.callout(
            f"Hebog history could not be loaded: {_history_error}",
            kind="warn",
        )
        if _history_error is not None
        else mo.md(
            "Choose a dataset and the registered Hebog runs to compare. "
            "Runs that do not contain the selected dataset are skipped."
        )
    )
    mo.vstack(
        [
            mo.md("## Hebog implementation history"),
            _history_status,
            history_dataset_selector,
            history_selector,
        ]
    )
    return history_dataset_selector, history_records, history_selector


@app.cell(hide_code=True)
def _(
    Path,
    history_dataset_selector,
    history_records,
    history_selector,
    load_campaign_cases,
    load_case_overlays,
    mo,
    np,
    plt,
    repository_root,
):
    _selected_history_case_id = history_dataset_selector.value
    mo.stop(
        _selected_history_case_id is None,
        mo.callout("Select a dataset to compare Hebog runs.", kind="warn"),
    )
    records_by_path = {
        str(_registered_run.get("campaign_repository_path")): _registered_run
        for _registered_run in history_records
    }
    selected_history_paths = tuple(history_selector.value or ())
    history_runs = []
    history_warnings = []
    for relative_path in selected_history_paths:
        history_root = (repository_root / Path(relative_path)).resolve()
        try:
            _, history_cases = load_campaign_cases(history_root)
            history_case = next(
                case
                for case in history_cases
                if case.case_id == _selected_history_case_id
            )
            history_image, _, history_overlays, _, run_warnings = (
                load_case_overlays(
                    history_case,
                    repository_root,
                    history_root,
                )
            )
            hebog_overlay = next(
                overlay
                for overlay in history_overlays.values()
                if overlay.finder_id == "hebog"
                and overlay.mode == "operational"
                and overlay.status == "success"
            )
            history_runs.append(
                (
                    records_by_path.get(str(relative_path), {}),
                    history_image,
                    hebog_overlay,
                )
            )
            history_warnings.extend(run_warnings)
        except (
            FileNotFoundError,
            KeyError,
            OSError,
            StopIteration,
            TypeError,
            ValueError,
        ) as error:
            history_warnings.append(f"{relative_path}: {error}")

    if history_runs:
        history_figure, history_axes = plt.subplots(
            1,
            len(history_runs),
            figsize=(6.2 * len(history_runs), 6.0),
            squeeze=False,
            sharex=True,
            sharey=True,
        )
        finite = history_runs[0][1][np.isfinite(history_runs[0][1])]
        minimum, maximum = (
            tuple(float(value) for value in np.percentile(finite, (1, 99.8)))
            if finite.size
            else (0.0, 1.0)
        )
        history_rows = []
        for axis, (_run_record, run_image, overlay) in zip(
            history_axes[0], history_runs, strict=True
        ):
            axis.imshow(
                run_image,
                origin="lower",
                cmap="gray",
                vmin=minimum,
                vmax=maximum,
                interpolation="nearest",
            )
            if overlay.support_mask is not None:
                axis.contourf(
                    overlay.support_mask,
                    levels=[0.5, 1.5],
                    colors=["tab:blue"],
                    alpha=0.2,
                    antialiased=False,
                )
                axis.contour(
                    overlay.support_mask,
                    levels=[0.5],
                    colors=["tab:blue"],
                    linewidths=0.8,
                )
            if overlay.source_x:
                axis.scatter(
                    overlay.source_x,
                    overlay.source_y,
                    s=30,
                    marker="o",
                    facecolors="none",
                    edgecolors="tab:blue",
                    linewidths=1.2,
                )
            if overlay.component_x:
                axis.scatter(
                    overlay.component_x,
                    overlay.component_y,
                    s=26,
                    marker="o",
                    facecolors="none",
                    edgecolors="tab:cyan",
                    linewidths=1.0,
                )
            run_label = str(_run_record.get("label", "Hebog run"))
            axis.set(
                title=(
                    f"{run_label}\n{overlay.source_count} associated sources | "
                    f"{overlay.component_count} Gaussian components | "
                    f"{overlay.label_count} support labels"
                ),
                xlabel="x pixel",
                ylabel="y pixel",
            )
            history_rows.append(
                "| "
                + " | ".join(
                    (
                        run_label.replace("|", "\\|"),
                        str(_run_record.get("commit") or "unrecorded")[:12],
                        str(
                            _run_record.get("source_tree_sha256") or "unknown"
                        )[:12],
                        str(
                            _run_record.get("hebog_runner_sha256")
                            or "unrecorded"
                        )[:12],
                        str(overlay.source_count),
                        str(overlay.component_count),
                        str(overlay.label_count),
                        (
                            f"{overlay.wall_seconds:.2f}"
                            if overlay.wall_seconds is not None
                            else "unavailable"
                        ),
                    )
                )
                + " |"
            )
        history_figure.suptitle(
            f"Hebog implementation comparison | {_selected_history_case_id}"
        )
        history_figure.tight_layout()
        history_output = mo.vstack(
            [
                mo.md(
                    "Zoom or pan any panel; shared axes keep all selected "
                    "Hebog runs synchronized. Blue regions are each run's "
                    "actual Rapthor support mask."
                ),
                mo.mpl.interactive(history_figure),
                mo.md(
                    "\n".join(
                        (
                            "| Run | Commit | Source tree | Runner | Associated sources | Gaussian components | Support labels | Wall time (s) |",
                            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
                            *history_rows,
                        )
                    )
                ),
            ]
        )
    else:
        history_output = mo.callout(
            "None of the selected Hebog campaigns contains this case.",
            kind="warn",
        )
    _history_warning_output = (
        mo.callout(
            "\n".join(f"- {warning}" for warning in history_warnings),
            kind="warn",
        )
        if history_warnings
        else mo.md("")
    )
    mo.vstack([history_output, _history_warning_output])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Interpretation for scientific review

    The first plot shows the selected input image. When Hebog background and
    RMS products are available, the next plot shows its local significance
    with the authoritative source-filtering mask outlined in black. Each
    remaining plot shows the same image with one successful finder's catalogue
    positions and support mask overlaid. Compare these plots to see where
    finders identify the same emission or produce different detections.

    Synthetic campaigns also provide a truth-layer selector. It can show every
    injected source or only one governed source subset, such as blended,
    extended, or image-edge sources. The default registered refresh has no
    injected truth. It overlays the latest source-identified Hebog run on the
    sealed released PyBDSF and Aegean reference results, without a selectable
    truth layer. The implementation-history section compares registered Hebog
    runs visually; it does not turn public observations into ground truth.

    These images are qualitative diagnostics. They complement, but do not
    replace, the campaign's governed completeness, reliability, astrometry,
    photometry, shape, association, and non-inferiority evidence. Public finder
    campaigns contain Hebog products only, so public reference comparisons must
    be presented from the separately compiled evidence rather than inferred
    from source counts in this notebook.
    """).callout(kind="info")
    return


if __name__ == "__main__":
    app.run()
