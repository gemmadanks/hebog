# Publish releases to PyPI

Hebog publishes new Release Please releases through
`.github/workflows/release-please.yaml`. Complete the account setup below before
merging the next release PR. The workflow does not upload older releases.

## Configure Trusted Publishing once

1. In the GitHub repository's **Settings → Environments**, create an environment
   named `pypi`. Restrict its deployment branches to `main`. The workflow runs
   from `main` even though it checks out the released commit. Leave required
   reviewers unset for automatic uploads after the release PR is merged.
2. If you already own the `hebog` project on PyPI, open its
   [Publishing settings](https://pypi.org/manage/project/hebog/settings/publishing/).
   Otherwise, add a pending publisher in your
   [account Publishing settings](https://pypi.org/manage/account/publishing/).
   A pending publisher creates the project on the first successful upload; it
   does not reserve the name. An existing project must be under your control.
3. Choose GitHub Actions and enter these exact values:

   | Field | Value |
   | --- | --- |
   | PyPI project name (pending publisher only) | `hebog` |
   | Repository owner | `gemmadanks` |
   | Repository name | `hebog` |
   | Workflow filename | `release-please.yaml` |
   | Environment name | `pypi` |

   The workflow field takes the filename, without `.github/workflows/`.
   No PyPI password or API-token secret is needed. GitHub supplies a short-lived
   identity token to the publishing job.

See PyPI's instructions for
[existing projects](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
and [pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

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
3. A separate `pypi` job downloads that artifact and uploads it with the PyPA
   publishing action, including metadata checks and the action's default
   attestations. Build or upload failures leave the GitHub release in place.

Publishing stays in the Release Please workflow because releases created with
`GITHUB_TOKEN` do not trigger a separate release-event workflow. Ordinary pushes
that only update the release PR skip building and publishing in this
workflow; normal CI still runs. New pushes do not cancel an active release run.

Check the **publish-pypi** job and the
[PyPI project page](https://pypi.org/project/hebog/) after publication. The
repository's existing `bump-minor-pre-major` setting keeps breaking-change
commits on minor bumps while the version is below `1.0.0`.

## Recover an interrupted release

For build or Trusted Publisher configuration failures, fix the cause and
choose **Re-run failed jobs** on the original release workflow run. This keeps
the successful Release Please job's release identity. Re-running every job or
pushing another commit may find no newly created release and skip publication.
If a code change is needed, prepare a new release; do not move the existing tag.

If the upload partially succeeded, inspect the PyPI file list and compare its
SHA-256 hashes with the retained artifact and publishing log before recovery.
The workflow deliberately fails on duplicate files. PyPI does not allow an
uploaded file to be overwritten: recover only missing files from the original
artifact through a maintainer-reviewed upload, or release a new version.
If the original artifact has expired, prepare a new release. Do not delete and
recreate a release tag to retry an upload.
