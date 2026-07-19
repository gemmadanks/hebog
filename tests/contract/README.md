# Contract tests

Contract tests define scheduler-independent public API, product, executor,
partition, and resource behaviour. Unimplemented Phase 0 specifications are
marked `xfail(strict=True)`: the expected failure keeps normal CI green, while
an unexpected pass fails CI until the test is reviewed and converted to a
normal assertion.

Run this lane with `just test-contract`.
