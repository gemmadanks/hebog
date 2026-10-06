# Contract tests

Contract tests define scheduler-independent public API, product, executor,
partition, and resource behaviour.
`config/contracts/phase-0-public-behaviours.json` names the test that holds
each frozen public behaviour and records whether it is implemented. An
unimplemented specification is marked `xfail(strict=True)`: the expected
failure keeps normal CI green, while an unexpected pass fails CI until the test
is reviewed, converted to a normal assertion, and its manifest status set to
`implemented`.

Run this lane with `just test-contract`.
