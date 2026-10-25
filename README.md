# DolphinForge

Build Flipper Zero apps (`.fap`) in the browser for **Official**, **Momentum** and **Unleashed**
firmware, latest or archived versions.

**→ [banimun.github.io/DolphinForge](https://banimun.github.io/DolphinForge/)**

## How it works

- Paste a GitHub link to a Flipper app, pick the firmwares and versions, hit **Build**.
- The app is compiled with ufbt in GitHub Actions, once per firmware, and the `.fap` files are
  ready to download a minute later.
- SDKs always come from each firmware's official distribution:

  | Firmware  | Latest                 | Archived versions                                  |
  |-----------|------------------------|----------------------------------------------------|
  | Official  | update.flipperzero.one | update.flipperzero.one/builds/firmware             |
  | Momentum  | up.momentum-fw.dev     | up.momentum-fw.dev/builds/firmware                 |
  | Unleashed | up.unleashedflip.com   | GitHub releases of DarkFlippers/unleashed-firmware |

- The app being built is third-party code, so the build runs with read-only access and no secrets.
