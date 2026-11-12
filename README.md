# Epsilon Desktop Pet

A Windows desktop pet based on the epsilon character from [Windowkill](https://store.steampowered.com/app/2782100/).


## Download

Get `epsilon_desktop_pet.exe` from the [Releases](releases) page.

As an unsigned binary, SmartScreen may show a warning on first launch — click
*More info* and then *Run anyway*.

## Run from source

```bat
git clone https://github.com/C-873/epsilon-desktop-pet.git
cd epsilon-desktop-pet
start.bat
```

`start.bat` needs Python 3.10–3.13 (64-bit) with `PyQt6` and `Pillow`:
if your system Python already has both, it runs directly; if not, the first
run downloads a portable Python with them (~130 MB, needs internet, no admin
rights).

## Controls

- **Follow the cursor** — on by default; it shoots its way toward it.
- **Drag** — move it by hand.
- **Double-click** (pet or tray icon) — toggle follow mode.
- **Right-click** — menu with *Follow cursor* and *Quit*.
- The **×** in the corner closes the pet.

## License

The code is released under [the Unlicense](LICENSE) — public domain, use and
modify it however you want.
