# DolphinForge

Kompilator aplikacji `.fap` dla Flipper Zero, działający na GitHub Pages i GitHub Actions.
Podajesz link do repo aplikacji, wybierasz firmware (Official, Momentum, Unleashed) i dostajesz
gotowe pliki do pobrania.

## Jak to działa

- `index.html` to strona (GitHub Pages). Twoim tokenem, z Twojej przeglądarki, odpala workflow w tym repo.
- `.github/workflows/build.yml` waliduje dane, buduje aplikację przez ufbt dla każdego firmware'u
  osobno i publikuje pliki `.fap` jako Release `build-<id>`.
- Budowany kod jest obcy, więc job budujący ma tylko odczyt i żadnych sekretów. Zapisuje wyłącznie
  job `release`, który nie uruchamia kodu aplikacji.

## Uruchomienie

1. Wrzuć zawartość tego folderu do nowego, **publicznego** repo na swoim koncie.
2. Settings → Pages → Source: *Deploy from a branch*, gałąź `main`, folder `/ (root)`.
3. Utwórz fine-grained token (Settings konta → Developer settings → Fine-grained tokens):
   - Repository access: tylko to repo
   - Permissions: **Actions: Read and write**, **Contents: Read-only**
4. Otwórz stronę `https://<login>.github.io/<repo>/`, w Ustawieniach wklej token i zapisz.

Link z gotowymi polami: `...?repo=owner/app&ref=main&dir=folder`.

## Testy

```
pip install pyyaml playwright
python3 tests/test_prepare.py   # walidacja danych w workflow
python3 tests/test_page.py      # strona w przeglądarce headless, z udawanym API GitHuba
```

## Plany

Wersja publiczna: backend na Cloudflare Workers trzymający token (bez tokena po stronie
użytkownika), limit buildów na osobę (Turnstile), sprzątanie starych release'ów.
