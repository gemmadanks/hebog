# Install Hebog

Hebog needs Python 3.12, 3.13 or 3.14 on Linux, macOS or Windows.

Hebog is not on PyPI yet. Install the latest tagged release from GitHub, or
replace the tag with the [release](https://github.com/gemmadanks/hebog/releases)
you want:

<!-- x-release-please-start-version -->

```console
pip install git+https://github.com/gemmadanks/hebog@v0.20.0
hebog --version
```

<!-- x-release-please-end -->

Pin the exact version in your environment. Hebog is experimental, and `0.x`
releases can change the API, the output format and the measurements. Releases
also appear on TestPyPI, but only to test packaging; do not install from there
for scientific work.

Dask is installed with Hebog. To run on a Dask cluster, install the same
Hebog version on the client and on every worker.

Next: [find sources in a FITS image](find-sources.md).

To work on Hebog itself, see [Contribute to Hebog](../how-to/index.md#set-up-a-source-checkout).
