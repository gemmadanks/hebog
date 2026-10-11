# Acceptance tests

This lane covers observable behaviour spanning Hebog, its materialised
products, Dask, and Rapthor-facing integration. Keep redistributable pull-
request scenarios small and deterministic.

Write scenarios in readable Given/When/Then form using normal pytest tests,
fixtures, and parametrization. `test_rapthor_scenarios.py` runs small
sectors through the Rapthor adapter: its products, a retried task, a lost
worker task, a refused sector, a cancelled analysis, and a dual run compared
with the frozen PyBDSF `master` products in `tests/data/pybdsf/`.
`config/contracts/phase-0-public-behaviours.json` names the test that holds
each behaviour, including the integration tests that assert the empty and
corrupt-input scenarios.

Mark every test `acceptance`. Add `slow` or `requires_data` when it belongs on
a controlled runner rather than pull-request CI. Do not add a Gherkin framework
unless domain experts will actively review or author feature files.
