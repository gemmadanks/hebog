# Publish releases to TestPyPI

Hebog publishes new Release Please releases through
`.github/workflows/release-please.yaml`. Complete the account setup below before
merging the next release PR. The workflow does not upload older releases.

Uploads go to [TestPyPI](https://test.pypi.org/project/hebog/), not PyPI,
while the public input envelope is limited to 1,024 pixels per side. That
exercises the complete release path without presenting Hebog as ready for
general installation; the installable artifact for users is the tagged GitHub
release. Move to PyPI when the envelope is useful beyond cut-outs, as
described at the end of this page.

## Configure Trusted Publishing once

1. In the GitHub repository's **Settings → Environments**, create an environment
   named `testpypi`. Restrict its deployment branches to `main`. The workflow
   runs from `main` even though it checks out the released commit. Leave
   required reviewers unset for automatic uploads after the release PR is
   merged.
2. TestPyPI accounts are separate from PyPI accounts. If you already own the
   `hebog` project there, open its
   [Publishing settings](https://test.pypi.org/manage/project/hebog/settings/publishing/).
   Otherwise, add a pending publisher in your
   [account Publishing settings](https://test.pypi.org/manage/account/publishing/).
   A pending publisher creates the project on the first successful upload; it
   does not reserve the name. An existing project must be under your control.
3. Choose GitHub Actions and enter these exact values:

   | Field | Value |
   | --- | --- |
   | Project name (pending publisher only) | `hebog` |
   | Repository owner | `gemmadanks` |
   | Repository name | `hebog` |
   | Workflow filename | `release-please.yaml` |
   | Environment name | `testpypi` |

   The workflow field takes the filename, without `.github/workflows/`.
   No password or API-token secret is needed. GitHub supplies a short-lived
   identity token to the publishing job.

See PyPI's instructions for
[existing projects](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
and [pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/);
they apply unchanged to TestPyPI.

## Publish a release

Review the [release boundaries](../reference/release-status.md#release-boundaries)
and the intended release's correctness inventory, supported envelope and
limitations before merging the Release Please PR. Keep experimental releases
explicitly scientifically unqualified. Upload automation does not establish
scientific parity or satisfy the later deployment gates.

Use the existing required PR checks as the release validation gate. `main`
requires up-to-date checks, including **Package smoke test**, which depends on
the full portable test matrix and exercises the installed public API. Do not
bypass those checks for release PRs. The publishing workflow relies on this
branch policy; it does not rerun CI or smoke-test its separately built files.

Release Please uses `GITHUB_TOKEN`, so its automatic PR updates do not start
CI. If required checks are missing, close and reopen the release PR as a
maintainer to trigger the existing `pull_request` workflow before merging.
See [Release Please's event behavior](https://github.com/googleapis/release-please-action#other-actions-on-release-please-prs).

After the release PR is merged:

1. Release Please creates the tag and GitHub release.
2. A build job checks out the exact released commit, runs
   `uv build --no-sources` and retains the wheel and source distribution as the
   `pypi-distributions` Actions artifact.
3. A separate `testpypi` job downloads that artifact and uploads it to
   TestPyPI with the PyPA publishing action, including metadata checks and the
   action's default attestations. Build or upload failures leave the GitHub
   release in place.

Publishing stays in the Release Please workflow because releases created with
`GITHUB_TOKEN` do not trigger a separate release-event workflow. Ordinary pushes
that only update the release PR skip building and publishing in this
workflow; normal CI still runs. New pushes do not cancel an active release run.

Check the **publish-testpypi** job and the
[TestPyPI project page](https://test.pypi.org/project/hebog/) after
publication. The repository's existing `bump-minor-pre-major` setting keeps
breaking-change commits on minor bumps while the version is below `1.0.0`.

To install a TestPyPI upload for a packaging check, fetch the artifact from
TestPyPI alone, then install that file so its dependencies resolve from PyPI,
which TestPyPI does not mirror:

```console
pip download --index-url https://test.pypi.org/simple/ --no-deps hebog==0.7.0
pip install ./hebog-0.7.0-py3-none-any.whl
```

Do not combine the two indexes with `--extra-index-url`. Pip then considers
candidates for `hebog` from both and may prefer a same-named project on PyPI,
which the pending publisher does not reserve.

## Recover an interrupted release

For build or Trusted Publisher configuration failures, fix the cause and
choose **Re-run failed jobs** on the original release workflow run. This keeps
the successful Release Please job's release identity. Re-running every job or
pushing another commit may find no newly created release and skip publication.
If a code change is needed, prepare a new release; do not move the existing tag.

If the upload partially succeeded, inspect the TestPyPI file list and compare
its SHA-256 hashes with the retained artifact and publishing log before
recovery. The workflow deliberately fails on duplicate files. An uploaded file
cannot be overwritten: recover only missing files from the original artifact
through a maintainer-reviewed upload, or release a new version. If the
original artifact has expired, prepare a new release. Do not delete and
recreate a release tag to retry an upload.

## Move to PyPI

When the supported input envelope makes general installation useful, add the
PyPI Trusted Publisher and GitHub environment with the same values as above,
then in `.github/workflows/release-please.yaml` rename the `publish-testpypi`
job and its environment to `pypi`, point the environment URL at
`https://pypi.org/project/hebog/` and remove the publishing step's
`repository-url`. Update the installation instructions in `README.md`, the
[quick start](../tutorials/index.md) and the
[release status](../reference/release-status.md) in the same change. A version
already uploaded to TestPyPI can be uploaded to PyPI unchanged; the indexes
are independent.
