# Publish releases to TestPyPI

Release Please publishes each release through
`.github/workflows/release-please.yaml`. Uploads go to
[TestPyPI](https://test.pypi.org/project/hebog/), not PyPI, while the public
envelope is 15,402 pixels a side: that exercises the complete release path
without presenting Hebog as ready for general installation, and the
installable artifact for users is the tagged GitHub release. The plan's task
13 moves uploads to PyPI.

## Configure Trusted Publishing once

1. In the repository's **Settings → Environments**, create `testpypi`,
   restrict its deployment branches to `main` (the workflow runs from `main`
   although it checks out the released commit) and leave required reviewers
   unset.
2. TestPyPI accounts are separate from PyPI accounts. Add a pending publisher
   in your
   [account Publishing settings](https://test.pypi.org/manage/account/publishing/)
   or, if the `hebog` project already exists under your control, in its
   [Publishing settings](https://test.pypi.org/manage/project/hebog/settings/publishing/).
   A pending publisher creates the project on the first upload; it does not
   reserve the name.
3. Choose GitHub Actions and enter these values. No token is needed: GitHub
   supplies a short-lived identity token to the publishing job.

   | Field | Value |
   | --- | --- |
   | Project name (pending publisher only) | `hebog` |
   | Repository owner | `gemmadanks` |
   | Repository name | `hebog` |
   | Workflow filename | `release-please.yaml` |
   | Environment name | `testpypi` |

PyPI's instructions for
[existing projects](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
and [pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
apply unchanged to TestPyPI.

## Publish a release

Before merging the Release Please PR, review the
[release boundaries](../reference/release-status.md#release-boundaries) and
the release's supported envelope and limitations; experimental releases stay
explicitly unqualified. The required PR checks on `main`, including
**Package smoke test** over the full portable matrix, are the release gate:
the publishing workflow does not rerun CI. Release Please uses
`GITHUB_TOKEN`, so its PR updates do not start CI; if checks are missing,
close and reopen the PR as a maintainer
([Release Please's event behaviour](https://github.com/googleapis/release-please-action#other-actions-on-release-please-prs)).
The PR also moves the install commands in `README.md`, the
[installation page](../tutorials/index.md) and the example below between
their `x-release-please` markers; never edit those versions by hand.

After the merge, Release Please creates the tag and GitHub release; a build
job checks out the released commit, runs `uv build --no-sources` and keeps
the wheel and source distribution as the `pypi-distributions` artifact; and
the `testpypi` job uploads that artifact with the PyPA publishing action, its
metadata checks and default attestations. A build or upload failure leaves
the GitHub release in place. Check the **publish-testpypi** job and the
TestPyPI project page afterwards. `bump-minor-pre-major` keeps breaking
changes on minor bumps below 1.0.0.

To check a TestPyPI upload, download it from TestPyPI alone and install the
file so that its dependencies resolve from PyPI, which TestPyPI does not
mirror. Never combine the indexes with `--extra-index-url`: pip may then
prefer a same-named PyPI project, which the pending publisher does not
reserve.

<!-- x-release-please-start-version -->

```console
pip download --index-url https://test.pypi.org/simple/ --no-deps hebog==0.18.0
pip install ./hebog-0.18.0-py3-none-any.whl
```

<!-- x-release-please-end -->

## Recover an interrupted release

For a build or publisher-configuration failure, fix the cause and choose
**Re-run failed jobs** on the original run, which keeps the release identity;
re-running every job or pushing another commit may find no new release and
skip publication. If a code change is needed, prepare a new release and never
move the tag. If an upload partially succeeded, compare the TestPyPI file
hashes with the retained artifact first: an uploaded file cannot be
overwritten, so recover only the missing files from the original artifact
through a maintainer-reviewed upload, or release a new version. Never delete
and recreate a tag to retry an upload.

## Move to PyPI

Add the PyPI Trusted Publisher and GitHub environment with the same values,
rename the `publish-testpypi` job and its environment to `pypi` in the
workflow, point the environment URL at `https://pypi.org/project/hebog/`,
remove the publishing step's `repository-url`, and update the installation
instructions in `README.md`, the installation page and the
[release status](../reference/release-status.md) in the same change. A
version already on TestPyPI can be uploaded to PyPI unchanged; the indexes
are independent.
