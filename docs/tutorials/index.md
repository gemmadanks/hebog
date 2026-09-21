# Install Hebog

Hebog needs Python 3.12, 3.13 or 3.14 on Linux, macOS or Windows.

Hebog is not on PyPI yet. Install a tagged
[release](https://github.com/gemmadanks/hebog/releases) from GitHub, replacing
the tag with the version you want:

```console
pip install git+https://github.com/gemmadanks/hebog@v0.12.0
hebog --version
```

Pin the exact version in your environment. Hebog is experimental, and `0.x`
releases can change the API, the output format and the measurements. Releases
also appear on TestPyPI, but only to test packaging; do not install from there
for scientific work.

Dask is installed with Hebog. To run on a Dask cluster, install the same
Hebog version on the client and on every worker.

Next: [find sources in a FITS image](find-sources.md).

To work on Hebog itself, see [Contribute to Hebog](../how-to/index.md#set-up-a-source-checkout).
