# DolphinForge

Build Flipper Zero apps (`.fap`) in the browser for **Official**, **Momentum** and **Unleashed**
firmware, latest or archived versions.

## How it works

- Paste a GitHub link to a Flipper app, pick the firmwares and versions, hit **Build**.
- Without any setup, Build opens a filled-in **Build an app** issue here. Submit it with your
  GitHub account; the app is built and the `.fap` files are posted in the issue a few minutes
  later. Up to 5 builds per account per day.
- With your own fork of DolphinForge and a fine-grained token for it (Actions and Contents: read
  and write), builds run in your fork, the page shows live progress and downloads the files
  itself, and you can also upload an app as a .zip or a folder.
- The app is compiled with ufbt in GitHub Actions, once per firmware.
- Builds are kept for 30 days, then removed.
- SDKs always come from each firmware's official distribution:

  | Firmware  | Latest                 | Archived versions                                  |
  |-----------|------------------------|----------------------------------------------------|
  | Official  | update.flipperzero.one | update.flipperzero.one/builds/firmware             |
  | Momentum  | up.momentum-fw.dev     | up.momentum-fw.dev/builds/firmware                 |
  | Unleashed | up.unleashedflip.com   | GitHub releases of DarkFlippers/unleashed-firmware |

- The app being built is third-party code, so the build runs with read-only access and no secrets.

## Credits

The starter app list in "Browse apps" draws on the catalog from
[joelewis012/flipper-fap-actions](https://github.com/joelewis012/flipper-fap-actions) (MIT).
