# Patches

Code changes to ReactOS, applied in name order with `git apply` before the build.
Name them `NNNN-short-description.patch` (e.g. `0001-classic-start-menu.patch`).

Make one from a ReactOS checkout at the pinned ref (see `upstream.env`):

```sh
git diff > ../os/patches/0001-my-change.patch
```

If ReactOS is moved to a newer release and a patch no longer applies, the build stops at
"Apply patches" and names the file.
