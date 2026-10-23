# Install Hebog

Hebog needs Python 3.12, 3.13 or 3.14 on Linux, macOS or Windows.

Install the latest release from [PyPI](https://pypi.org/project/hebog/)
(releases before 0.22.0 are on
[GitHub](https://github.com/gemmadanks/hebog/releases) only):

<!-- x-release-please-start-version -->

```console
pip install hebog==0.25.0
hebog --version
```

<!-- x-release-please-end -->

Pin the exact version in your environment. Hebog is experimental, and `0.x`
releases can change the API, the output format and the measurements.

Dask is installed with Hebog. To run on a Dask cluster, install the same
Hebog version on the client and on every worker.

Next: [find sources in a FITS image](find-sources.md).

To work on Hebog itself, see [Contribute to Hebog](../how-to/index.md#set-up-a-source-checkout).
