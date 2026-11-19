# Digitalizace videa – skill pro Claude Code

Claude video jako celek nevidí. Tenhle skill mu ho „pustí“ jinak: video z YouTube nebo z disku
převede na **snímky a přepis s časy**, spojí je do jednoho Markdownu a Claude z toho napíše
čitelný **zápis**. Hodí se na návody (háčkování, vaření, opravy), přednášky i recenze.

**Aktuální verze: 0.1.0 (19. 11. 2026).** Přehled změn v [CHANGELOG.md](CHANGELOG.md).

## Jak to funguje

1. `yt-dlp` stáhne video (max 720p) a popis s kapitolami. V popisu bývá odkaz na psaný návod.
2. Přepis: titulky z YouTube, když existují (titulky autora mají přednost před automatickými).
   Když chybí, zvuk se přepíše lokálně whisperem (whisper.cpp).
3. `ffmpeg` vybere snímky. Hustota je volitelná:
   - `auto` (výchozí): snímek při změně scény, nejpozději po 20 s,
   - `ridka` 30 s, `stredni` 10 s, `husta` 3 s, nebo libovolné číslo v sekundách.
4. Vzniknou přehledové listy po 12 snímcích. Claude si projde celé video za pár obrázků
   a plné snímky otevírá jen tam, kde potřebuje detail.
5. Claude přečte `video.md` (snímky proložené přepisem), ověří titulky proti obrazu
   a napíše `zapis.md`: u návodu materiál a kroky s časy, u přednášky hlavní body.

Výstup jde do `~/Movies/digitalizace/<datum>-<název>/`. Změní se proměnnou `DIGITALIZACE_VYSTUP`
nebo parametrem `--vystup`.

## Instalace

Potřebuje Claude Code (pouští lokální nástroje, v claude.ai na webu nefunguje).

```bash
brew install yt-dlp ffmpeg whisper-cpp
```

Whisper je potřeba jen pro videa bez titulků. Model (např. `ggml-large-v3-turbo-q5_0.bin`)
stáhni z [huggingface.co/ggerganov/whisper.cpp](https://huggingface.co/ggerganov/whisper.cpp)
do `~/.cache/whisper-models/`, nebo cestu nastav v proměnné `WHISPER_MODEL`.

Skill přidáš jako plugin:

```
/plugin marketplace add ondrnovy/digitalizace-videa-skill
/plugin install digitalizace-videa@digitalizace-videa-skill
```

Nebo naklonuj repo a složku `skills/digitalizace-videa` nalinkuj do `~/.claude/skills/`.

## Použití

Stačí Claudovi poslat odkaz: „zdigitalizuj tohle video“, „vytáhni z videa návod“,
„shrň mi tohle video“. Na hustotu snímků se dá říct rovnou: „hustě, chci vidět detaily rukou“.

Skript jde pustit i ručně:

```bash
python3 skills/digitalizace-videa/scripts/digitalizuj.py "https://youtu.be/…" --hustota stredni
```

## Omezení

- Mezi snímky Claude nic nevidí. Rychlý pohyb zachytí jen hustší běh, případně jen na vybraný úsek.
- Automatické titulky dělají chyby v číslech a odborných slovech. Skill je proto ověřuje proti
  obrazu a popisu a nejistoty vypisuje zvlášť.
- Video s obrazem i zvukem umí přímo zpracovat Gemini. Na rychlé shrnutí cizího videa stačí.
  Tenhle skill je na případ, kdy chcete s obsahem dál pracovat v Claude.

## Licence

MIT
