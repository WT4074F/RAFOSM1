# Ashwood (working name)

Our own desktop OS built on [ReactOS](https://reactos.org): the Windows Classic look, new desktop ideas
(a sidebar, a richer Explorer, WinFS-style search via FortFS), and no Aero or glass.

> **Honest limit:** it is exactly as stable as the ReactOS release it's built on. We fix bugs we can
> reproduce, but we aren't promising to make ReactOS stable.

"Ashwood" is a placeholder. Rename the OS by editing [`brand/brand.ini`](brand/brand.ini) and rebuilding.

## How it's built

This repo doesn't contain a copy of ReactOS. Each build on GitHub Actions:

1. checks out the ReactOS release pinned in [`upstream.env`](upstream.env) (currently 0.4.16)
2. applies our changes, in this order:
   - [`patches/`](patches): code changes as `git` patches
   - [`overlay/`](overlay): whole files copied over the source tree
   - [`brand/`](brand): renames the product in the boot menu, setup and registry, and redraws the boot logos
3. builds the toolchain (RosBE) and the ISO the same way ReactOS's own CI does
4. boots the ISO in QEMU and saves screenshots, so a build that doesn't boot fails
5. uploads the ISO with `CREDITS.txt` and the ReactOS licence files

The first build takes a couple of hours because the toolchain is compiled from source. After that it's cached.

**Get an ISO:** open the **Actions** tab → latest green **Build** run → download the
`ashwood-i386-Release-…` artifact. The `boot-test-…` artifact has the QEMU screenshots and a report of
every string the branding changed. Push a tag like `v0.1` to publish a GitHub release instead.

## Try it in VirtualBox (Windows)

```powershell
cd tools
.\New-DevVM.ps1 -Iso "$HOME\Downloads\ashwood-0.1-i386-Release-xxxxxxx.iso" -Start
```

This makes a 32-bit VM with 1 GB RAM, a 20 GB disk on IDE, and PCnet networking (the hardware ReactOS
handles best). It won't touch a VM that already exists unless you pass `-Replace`, and then it asks first.
If PowerShell blocks the script, run `Set-ExecutionPolicy -Scope Process Bypass` in that window first.

## Roadmap

1. **Automated build, branded boot and setup, installs in VirtualBox** ← now
2. Classic desktop defaults: wallpaper, icons, apps, UK keyboard, a redesigned Start menu in the classic look
3. Desktop sidebar, classic styling, can be turned off
4. Explorer: This PC with drives, large icons, previews, details pane
5. FortFS part 1: property search, tags, smart collections
6. FortFS part 2: places, people, links between files

We don't start a milestone until the build is green.

## Rules we keep

- ReactOS's licences stay intact and ReactOS is credited (see [CREDITS.md](CREDITS.md)).
- No Microsoft files, artwork or logos, and no ReactOS name or logo on our branding.
- All artwork in this repo is original (the boot logo is drawn from text at build time).

## Licence

Our scripts and changes are GPL-2.0-or-later, the same as ReactOS. See [LICENSE](LICENSE).
