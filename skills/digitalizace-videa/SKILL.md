---
name: digitalizace-videa
description: Digitalizace videa (YouTube odkaz nebo lokální soubor) do textu. Stáhne video, vybere snímky, vezme titulky nebo přepíše zvuk whisperem a spojí to podle času do jednoho Markdownu. Z něj pak Claude napíše čitelný zápis (návod, postup, shrnutí). Hustota snímků je volitelná. Použij, když uživatel pošle YouTube odkaz nebo video a chce ho „zdigitalizovat“, „přepsat“, „vytáhnout z něj návod“, „shrnout video“, „udělat z videa zápis“, „koukni na tohle video“, „co je v tom videu“. Na krátké záznamy obrazovky s bleskovými stavy UI je lepší extrakce s hustým fps.
---

# Digitalizace videa

Claude video jako celek nevidí. Proto: **snímky + přepis s časy → jeden Markdown → zápis.**
Nikdy netvrď, co ve videu je, dokud jsi neprošel přepis a snímky.

## 1. Spustit skript

```bash
python3 -I <složka skillu>/scripts/digitalizuj.py "<URL nebo cesta>" [--hustota H] [--prepis P] [--vystup DIR]
```

Spouštěj z domovské složky, ne ze složky s videem. Na konci skript vypíše JSON se `slozka`,
počtem snímků a zdrojem přepisu.

| Parametr | Hodnoty | Výchozí |
|---|---|---|
| `--hustota` | `auto` = snímek při změně scény, nejpozději po 20 s · `ridka` 30 s · `stredni` 10 s · `husta` 3 s · číslo = sekundy | `auto` |
| `--prepis` | `auto` = titulky z YouTube, když nejsou, whisper · `titulky` · `whisper` · `zadny` | `auto` |
| `--vystup` | složka výstupu | `$DIGITALIZACE_VYSTUP/<datum>-<název>/`, bez proměnné `~/Movies/digitalizace/…` |

Volba hustoty: **mluvené video, přednáška, slajdy → `auto`**. U ruční práce, kde záleží na pohybu
(háčkování, vaření, oprava), a když uživatel chce vidět detaily → `stredni` nebo `husta`,
případně jen na úsek. Když hustotu neřekl, jeď `auto` a nabídni hustší běh, kdyby něco chybělo.

Opakovaný běh do stejné složky video znovu nestahuje, jen přepíše snímky, `video.md` a `prepis.md`.
Jiná hustota = spustit znovu s jiným `--hustota`.

Výstup:
- `video.md`: hlavička (zdroj, kapitoly, **popis videa**: bývá v něm odkaz na psaný návod),
  seznam přehledových listů, pak pro každý snímek `## HH:MM:SS`, obrázek a text řečený do dalšího snímku.
- `prepis.md`: čistý přepis po 30s odstavcích.
- `prehledy/NN.jpg`: přehledové listy, 12 zmenšených snímků na list (4×3, po řádcích). Který
  snímek je na kterém listu, je ve `video.md`.
- `snimky/NNNN_tHH-MM-SS.jpg` (max šířka 1280), `meta.json`, `video.mp4`.

## 2. Projít

1. Přečti celý `video.md`, tedy přepis, kapitoly a popis.
2. Snímky: **nejdřív přehledové listy** (`prehledy/*.jpg`). Jeden list = 12 snímků za cenu jednoho
   obrázku. Plné snímky otevírej jen tam, kde potřebuješ detail nebo kde přepis odkazuje na obraz
   („takhle“, „vidíte tady“, „this stitch“). Kde je potřeba víc detailu, než má výběr, vytáhni
   snímky jen z úseku do dočasné složky:
   `ffmpeg -ss 02:10 -to 02:40 -i video.mp4 -vf fps=1 -q:v 3 <tmp>/u_%03d.jpg`.
3. Automatické titulky mají chyby, hlavně v číslech a odborných slovech. Ověř je proti obrazu,
   popisu a kapitolám. Spočítej, co se spočítat dá (počty, součty, rozměry).

## 3. Zápis

Do stejné složky napiš **`zapis.md`** v jazyce uživatele. Jeho tvar se řídí typem videa:
- **návod / postup** (ruční práce, recept, oprava): materiál a nástroje, pak očíslované kroky,
  u každého kroku čas `[02:10]` a odkaz na klíčový snímek, tipy a chyby, na které autor upozorňuje,
- **přednáška / rozhovor**: hlavní body, citace s časem, závěr,
- **prezentace produktu / recenze**: fakta, čísla, plusy a minusy.

Nahoře zdroj, autor, délka a odkaz na psaný originál, pokud je v popisu. Na konec sekce
`## Nejisté / neověřené` (nejasné číslo v titulcích, dopočítané hodnoty). Odborné termíny uváděj
přeložené i v originále, např. „sloupek (double crochet, US)“.

## 4. Předat

- Řekni uživateli cestu k `zapis.md`, počet snímků, zdroj přepisu a co bylo nejisté.
- Kam zápis trvale uložit, rozhoduje uživatel. Zeptej se ho a obsah zkopíruj až na jeho slovo.
- `video.mp4` ve složce zůstává pro případ dalšího běhu. Nemaž ho bez dotazu, ale zmiň jeho velikost.

## Závislosti a známé potíže

- `yt-dlp`, `ffmpeg`, `whisper-cli` (whisper.cpp), na macOS `brew install yt-dlp ffmpeg whisper-cpp`.
  Model whisperu: proměnná `WHISPER_MODEL`, výchozí
  `~/.cache/whisper-models/ggml-large-v3-turbo-q5_0.bin`
  ([modely](https://huggingface.co/ggerganov/whisper.cpp)). Bez modelu fungují jen titulky.
- **`ffmpeg` hlásí `dyld: Library not loaded … libx265`** → po jiném `brew install` se rozjely
  knihovny, pomůže `brew upgrade ffmpeg`.
- YouTube občas odmítne stahovat titulky (HTTP 429). Skript v režimu `auto` pak přejde na whisper.
  Whisper je náročný na CPU (jednotky minut na 15 min videa). Na slabém nebo vytíženém stroji
  použij `--prepis zadny`, nebo přepis pusť jinde.
- YouTube odkaz s obrazem i zvukem umí přímo zpracovat Gemini. Na rychlé shrnutí cizího videa
  to stačí. Tenhle skill je na případ, kdy se s obsahem dál pracuje v Claude.
