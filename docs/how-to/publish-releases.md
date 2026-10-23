# Publish releases to PyPI

Release Please publishes each release through
`.github/workflows/release-please.yaml` to
[PyPI](https://pypi.org/project/hebog/), as experimental `0.x` releases
with an alpha classifier, so that Rapthor's optional Hebog dependency
installs from the usual index; releases before 0.22.0 are on GitHub and
TestPyPI only.

## Configure Trusted Publishing once

1. In the repository's **Settings → Environments**, create `pypi`,
   restrict its deployment branches to `main` (the workflow runs from `main`
   although it checks out the released commit) and leave required reviewers
   unset.
2. Add a pending publisher in your PyPI
   [account Publishing settings](https://pypi.org/manage/account/publishing/)
   or, once the `hebog` project exists, in its
   [Publishing settings](https://pypi.org/manage/project/hebog/settings/publishing/).
   A pending publisher creates the project on the first upload; it does not
   reserve the name, so publish the first release soon after adding it.
3. Choose GitHub Actions and enter these values. No token is needed: GitHub
   supplies a short-lived identity token to the publishing job.

   | Field | Value |
   | --- | --- |
   | Project name (pending publisher only) | `hebog` |
   | Repository owner | `gemmadanks` |
   | Repository name | `hebog` |
   | Workflow filename | `release-please.yaml` |
   | Environment name | `pypi` |

PyPI's instructions cover
[existing projects](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
and [pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).
The `testpypi` environment and TestPyPI publisher are no longer used and can
be deleted.

## Publish a release

Before merging the Release Please PR, review the
[release boundaries](../reference/release-status.md#release-boundaries) and
the release's supported envelope and limitations; experimental releases stay
explicitly unqualified. The required PR checks on `main`, including
**Package smoke test** over the full portable matrix and all applicable
checks, are the release gate (see [PR feedback](index.md#pull-request-feedback)):
the publishing workflow does not rerun CI. Release Please uses
`GITHUB_TOKEN`, so its PR updates do not start CI; if checks are missing,
close and reopen the PR as a maintainer
([Release Please's event behaviour](https://github.com/googleapis/release-please-action#other-actions-on-release-please-prs)).
The PR also moves the install commands in `README.md`, the
[installation page](../tutorials/index.md) and the example below between
their `x-release-please` markers; never edit those versions by hand.

A release on PyPI is permanent, so make sure the
[release check](../reference/domain-glossary.md) covers what ships. If it ran on an earlier commit, check that `main` has changed no
package code or dependencies since, apart from docstrings and comments:

```console
git diff --stat CHECKED_COMMIT origin/main -- src/hebog pyproject.toml uv.lock ':!src/hebog/validation'
```

If anything else changed, run the release check again before merging.

After the merge, Release Please creates the tag and GitHub release; a build
job checks out the released commit, runs `uv build --no-sources` and keeps
the wheel and source distribution as the `pypi-distributions` artifact; and
the `pypi` job uploads that artifact with the PyPA publishing action, its
metadata checks and default attestations. A build or upload failure leaves
the GitHub release in place. Check the **publish-pypi** job and the PyPI
project page afterwards, then install the release into a fresh environment.
Below 1.0.0, `bump-minor-pre-major` bumps the minor version for features
and breaking changes alike, and the patch version for fixes; the release
notes mark which changes break callers.

<!-- x-release-please-start-version -->

```console
pip install hebog==0.24.0
hebog --version
```

<!-- x-release-please-end -->

## Recover an interrupted release

For a build or publisher-configuration failure, fix the cause and choose
**Re-run failed jobs** on the original run, which keeps the release identity;
re-running every job or pushing another commit may find no new release and
skip publication. If a code change is needed, prepare a new release and never
move the tag. If an upload partially succeeded, compare the PyPI file hashes
with the retained artifact first: an uploaded file cannot be
overwritten, so recover only the missing files from the original artifact
through a maintainer-reviewed upload, or release a new version. Never delete
and recreate a tag to retry an upload.

## Withdraw a release

PyPI never lets a file be replaced or a version number reused, even after
the release is deleted. If a published release is wrong, for example it
fails to install or gives incorrect results, yank it instead of deleting
it: on PyPI, open the project's **Releases**, choose **Options → Yank** for
that version and give the reason. Installs that pin the version exactly
still get it; all others skip it. Say why in the GitHub release notes and
publish the fix as the next release.
