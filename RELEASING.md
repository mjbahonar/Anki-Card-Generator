# Release policy

The supported application is `main.py`; its version is `main.VERSION`. English and Norwegian use the same release sequence.

## Naming and compatibility

- Use semantic versions with three components: `MAJOR.MINOR.PATCH`.
- Use lowercase, annotated Git tags: `v4.0.1`. No language suffixes and no two-component tags for new releases.
- Increment PATCH for fixes, documentation and cleanup that retain the supported V4 workflow; MINOR for backward-compatible functionality; MAJOR for incompatible changes to the supported configuration, CLI or Anki schema.
- Use prerelease suffixes when needed, for example `v4.1.0-rc.1`; mark those GitHub releases as prereleases.
- Preserve published tags and historical naming. Never move, replace or force-push a release tag to include a later fix.

## Release checklist

1. Review the final diff and working tree. Set `main.VERSION` to the release number.
2. Add dated release notes to `CHANGELOG.md`; update English/Persian READMEs when behavior or usage changes. State known limitations and what was actually tested.
3. Run `python -m unittest test_v4 test_lexin_scraper -v`, `python main.py --check`, and `git diff --check`. Live-test changed adapters where access allows; report unavailable services honestly.
4. Commit the tested change on `main`. Create the annotated `vX.Y.Z` tag at that commit.
5. Push `main` and that exact tag, without force. Publish a GitHub release titled `vX.Y.Z` targeting that tag, using the same changelog notes. Do not attach personal input workbooks, generated decks or credentials.
6. Verify the remote branch, tag and published release. Report the release URL and any remaining limitations.

A Git tag and a GitHub release are separate objects. Do not describe a tag-only push as a published GitHub release.
