# Releasing RFHound

Publishing to PyPI is automated by [`.github/workflows/publish.yml`](../.github/workflows/publish.yml)
via **Trusted Publishing** (OIDC) — no API token is stored.

## One-time PyPI setup

On <https://pypi.org/manage/account/publishing/>, add a *pending publisher*:

| Field | Value |
|---|---|
| PyPI project name | `rfhound` |
| Owner | `jawaman14` |
| Repository name | `rfhound` |
| Workflow filename | `publish.yml` |
| Environment name | `pypi` |

Then, in the GitHub repo, create an **Environment** named `pypi`
(Settings → Environments) — optionally with a required reviewer so a human
approves each publish.

> Prefer an API token instead? See the comment block at the top of
> `publish.yml` for the two-line change and set a `PYPI_API_TOKEN` secret.

## Cutting a release

1. Bump the version in `pyproject.toml` **and** `rfhound/__init__.py` (keep them
   in sync — the workflow fails the build if the tag ≠ the package version).
2. Update `CHANGELOG.md` (date the new section) and the README test count.
3. Commit, then tag and push:
   ```bash
   git tag v1.3.0
   git push origin v1.3.0
   ```
4. The workflow runs the test suite, builds the sdist + wheel, `twine check`s
   them, **creates the GitHub Release** (notes auto-extracted from the matching
   `## [x.y.z]` section of `CHANGELOG.md`, with the wheel + sdist attached), and
   publishes to PyPI. Watch it under the repo's **Actions** tab.

Because the release body comes straight from the CHANGELOG, keeping that file
current is all that's needed — there's no separate release-notes step to write.

A GitHub *Release* published from the tag also triggers the workflow, so you can
release from the GitHub UI instead of pushing a tag if you prefer.
