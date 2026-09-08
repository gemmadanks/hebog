"""Serial/existing-Dask equivalence of synthetic R6 missing-support records."""

# pyright: reportUnknownVariableType=false

from __future__ import annotations

import importlib
import runpy
import sys
from dataclasses import replace
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from distributed import Client, LocalCluster

from hebog.executors import SerialExecutor
from hebog.executors.dask import DaskExecutor
from hebog.validation.external_runners import canonical_sha256

_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_ROOT))
worker: Any = importlib.import_module(
    "scripts.validation.source_catalogue_campaign_worker"
)


@pytest.mark.integration
def test_missing_source_support_survives_exact_record_compiler_and_dask() -> (
    None
):
    fixture = runpy.run_path(
        str(
            _ROOT / "tests/unit/validation/test_source_support_availability.py"
        )
    )["support_availability_fixture"]
    batches = [
        fixture(finder)
        for finder in (
            "current-hebog",
            "incumbent-hebog",
            "released-pybdsf",
            "pinned-pybdsf-master",
        )
    ]
    specifications = tuple(
        SimpleNamespace(
            endpoint_id=metric, metric_family=metric, stratum="overall"
        )
        for metric in (
            "completeness",
            "reliability",
            "integrated-flux-median",
            "mask-recall",
        )
    )
    # Publish the truth mask too: native publication and exclusive ownership
    # remain distinct, and the R6 compiler must score the actual public mask.
    publication = batches[0].truth_labels > 0
    batches = [
        replace(batch, stage_masks={"publication": publication})
        for batch in batches
    ]
    compile_record = partial(
        worker.compile_continuum_record,
        publication=publication,
        specifications=specifications,
    )
    serial = SerialExecutor().map_batches(compile_record, batches)
    with (
        LocalCluster(
            n_workers=2,
            threads_per_worker=1,
            processes=False,
            dashboard_address=None,  # pyright: ignore[reportArgumentType]
        ) as cluster,
        Client(cluster) as client,
    ):
        distributed = DaskExecutor(client).map_batches(compile_record, batches)
        assert client.status == "running"
        assert distributed == serial
        # A corrupt asserted label still fails remotely, not as an empty row.
        corrupt = replace(
            batches[0],
            sources=(replace(batches[0].sources[1], support_label=9),),
        )
        with pytest.raises(ValueError, match="absent"):
            DaskExecutor(client).map_batches(compile_record, [corrupt])
    for record in serial:
        assert record["record_sha256"] == canonical_sha256(
            {
                key: value
                for key, value in record.items()
                if key != "record_sha256"
            }
        )
        assert record["source_diagnostics"][
            "unavailable_source_support_ids"
        ] == ["dominated", "extra"]
        observations = record["continuum_observations"]
        assert observations["completeness"]["values"] == [1.0]
        assert observations["reliability"]["values"] == [pytest.approx(2 / 3)]
        assert observations["mask-recall"]["values"] == [1.0]
