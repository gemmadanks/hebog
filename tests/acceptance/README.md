# Acceptance tests

This lane covers observable behaviour spanning Hebog, its materialised
products, Dask, and Rapthor-facing integration. Keep redistributable pull-
request scenarios small and deterministic.

Write scenarios in readable Given/When/Then form using normal pytest tests,
fixtures, and parametrization. The scenarios here are strict-xfail
placeholders for the Rapthor adapter's products, restart and retry behaviour,
backend selection and dual-run comparison;
`config/contracts/phase-0-public-behaviours.json` names the integration tests
that already assert the empty and corrupt-input scenarios.

Mark every test `acceptance`. Add `slow` or `requires_data` when it belongs on
a controlled runner rather than pull-request CI. Do not add a Gherkin framework
unless domain experts will actively review or author feature files.
