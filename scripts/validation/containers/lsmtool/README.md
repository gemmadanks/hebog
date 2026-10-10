# Pinned LSMTool container

This recipe builds the Linux runtime in which
`scripts/validation/check_lsmtool_filter.py` runs pinned LSMTool's
`filter_sources` on products the Rapthor adapter wrote on the host. It holds
LSMTool at commit `9bac2f7` (the pin of the
[Rapthor source-finding contract](../../../../docs/reference/rapthor-source-finding-contract.md))
and its dependencies, not Hebog.

| File | Purpose |
| --- | --- |
| `Containerfile` | Ubuntu 24.04 on `linux/amd64`, an LSMTool wheel built from the archive of the pinned commit, and LSMTool's dependencies |
| `requirements-lsmtool-build.in`, `.txt` | The wheel builder's backend, pinned with hashes |
| `requirements-lsmtool-runtime.in`, `.txt` | LSMTool's dependencies, pinned with hashes for Python 3.12 on `x86_64-manylinux_2_39` |

bdsf, python-casacore and everybeam publish Linux wheels for x86-64 only, so
the image is `linux/amd64` and runs under Rosetta on Apple silicon. There,
`import everybeam` fails with an illegal instruction; `filter_sources`
without a beam Measurement Set never imports it.

## Build

Archive the pinned commit from an LSMTool checkout, check that the archive
holds it, and build from a temporary context:

```console
context=$(mktemp -d)
cp Containerfile requirements-lsmtool-*.txt "$context"
git -C <LSMTool checkout> archive --output="$context/lsmtool.tar" \
  9bac2f7fabdc15cd9490acfeb9c292aa72af59b7
test "$(git get-tar-commit-id < "$context/lsmtool.tar")" = \
  9bac2f7fabdc15cd9490acfeb9c292aa72af59b7
podman build --platform linux/amd64 --file "$context/Containerfile" \
  --tag localhost/hebog-lsmtool:9bac2f7 "$context"
```

The build takes about 90 seconds and the image is about 800 MB. Regenerate
the `.txt` files with `uv pip compile <file>.in --python-version 3.12
--python-platform x86_64-manylinux_2_39 --only-binary :all:
--generate-hashes --no-header --annotation-style line -o <file>.txt`.
