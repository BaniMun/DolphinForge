# DolphinForge

Build Flipper Zero apps (`.fap`) in the browser for **Official**, **Momentum** and **Unleashed**
firmware, latest or archived versions. Runs on GitHub Pages + GitHub Actions, no server.

## How it works

- `index.html` is the web page (GitHub Pages). With your token, from your browser, it starts the
  build workflow in this repo and shows progress, errors and download links.
- `.github/workflows/build.yml` validates the input, builds the app with ufbt once per firmware
  and publishes the `.fap` files as a pre-release tagged `build-<id>`.
- SDKs always come from each firmware's official distribution:

  | Firmware  | Latest                     | Archived versions                                   |
  |-----------|----------------------------|-----------------------------------------------------|
  | Official  | update.flipperzero.one     | update.flipperzero.one/builds/firmware/<version>/   |
  | Momentum  | up.momentum-fw.dev         | up.momentum-fw.dev/builds/firmware/<version>/       |
  | Unleashed | up.unleashedflip.com       | GitHub releases of DarkFlippers/unleashed-firmware  |

- The app being built is third-party code, so the build job has read-only access and no secrets.
  Only the `release` job can write, and it never runs the app's code.

## Setup

1. Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/ (root)`.
2. Create a fine-grained token (Account settings → Developer settings → Fine-grained tokens):
   - Repository access: only this repo
   - Permissions: **Actions: Read and write**, **Contents: Read-only**
3. Open `https://<login>.github.io/DolphinForge/`, paste the token in Settings and save.

Prefilled link: `...?repo=owner/app&ref=main&dir=folder`.

## Tests

```
pip install pyyaml playwright
python3 tests/test_prepare.py   # workflow input validation and SDK URLs
python3 tests/test_page.py      # the page in a headless browser against a fake GitHub API
```

## Roadmap

Public version: a Cloudflare Worker holding the token (no token on the user side), per-user
build limits (Turnstile), cleanup of old build releases.
