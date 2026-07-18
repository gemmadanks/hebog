# Acceptance tests

This lane covers observable behaviour spanning Hebog, its materialised
products, Dask, and Rapthor-facing integration. Keep redistributable pull-
request scenarios small and deterministic.

Write scenarios in readable Given/When/Then form using normal pytest tests,
fixtures, and parametrization. Initial scenarios cover empty and corrupt
inputs, restart and retry behaviour, backend selection, dual-run comparison,
and retained/rejected sky-model decisions.

Mark every test `acceptance`. Add `slow` or `requires_data` when it belongs on
a controlled runner rather than pull-request CI. Do not add a Gherkin framework
unless domain experts will actively review or author feature files.
