#!/usr/bin/env python3
"""Digitalizace videa: YouTube URL nebo lokální soubor -> snímky + přepis s časy.

Výstup (složka --vystup):
  video.mp4        stažené video (při opakovaném běhu se znovu nestahuje)
  snimky/          NNNN_tHH-MM-SS.jpg
  video.md         snímky proložené přepisem, podklad pro čtení
  prepis.md        čistý přepis s časovými značkami po odstavcích
  meta.json        metadata, zdroj přepisu, hustota, počet snímků
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

WHISPER_MODEL = Path(os.environ.get(
    "WHISPER_MODEL", Path.home() / ".cache/whisper-models/ggml-large-v3-turbo-q5_0.bin")).expanduser()
DEFAULT_ROOT = Path(os.environ.get(
    "DIGITALIZACE_VYSTUP", Path.home() / "Movies/digitalizace")).expanduser()
PRESETY = {"ridka": 30.0, "stredni": 10.0, "husta": 3.0}
AUTO_SCENA = 0.3
AUTO_MAX_MEZERA = 20.0
ODSTAVEC_S = 30.0
PREHLED_SLOUPCE = 4
PREHLED_RADKY = 3


def run(cmd, capture):
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if r.returncode != 0:
        err = (r.stderr or "")[-2000:] if capture else ""
        sys.exit(f"Selhalo: {' '.join(map(str, cmd[:3]))} …\n{err}")
    return r


def slug(text):
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:50].rstrip("-") or "video"


def hms(sec):
    s = int(sec)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_hustota(value):
    if value == "auto":
        return None
    if value in PRESETY:
        return PRESETY[value]
    try:
        n = float(value.replace(",", "."))
    except ValueError:
        sys.exit(f"Neznámá hustota '{value}': auto | ridka | stredni | husta | <sekundy>")
    if n <= 0:
        sys.exit("Hustota v sekundách musí být > 0")
    return n


def youtube_info(url):
    r = run(["yt-dlp", "-J", "--no-playlist", url], True)
    return json.loads(r.stdout)


def stahni_video(url, cil):
    if cil.exists():
        return
    run(["yt-dlp", "--no-playlist", "-q", "--no-progress", "-f", "bv*[height<=720]+ba/b[height<=720]/b",
         "--merge-output-format", "mp4", "-o", str(cil), url], False)


def vyber_titulky(info):
    lang = (info.get("language") or "").split("-")[0]
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    if lang:
        for k in manual:
            if k == lang or k.startswith(lang + "-"):
                return k, False
    if manual and not lang:
        return next(iter(manual)), False
    for k in (f"{lang}-orig", lang):
        if lang and k in auto:
            return k, True
    return None, False


def stahni_titulky(url, jazyk, automaticke, slozka):
    for f in slozka.glob("titulky.*"):
        f.unlink()
    flag = "--write-auto-subs" if automaticke else "--write-subs"
    r = subprocess.run(["yt-dlp", "--no-playlist", "--skip-download", flag,
                        "--sub-langs", jazyk, "--sub-format", "json3",
                        "-o", str(slozka / "titulky"), url],
                       capture_output=True, text=True)
    soubory = list(slozka.glob("titulky*.json3"))
    if r.returncode != 0 or not soubory:
        return None
    return soubory[0]


def kusy_z_json3(soubor):
    data = json.loads(soubor.read_text(encoding="utf-8"))
    kusy = []
    for ev in data.get("events", []):
        start = ev.get("tStartMs", 0)
        for i, seg in enumerate(ev.get("segs") or []):
            text = seg.get("utf8", "").replace("\n", " ")
            if i == 0:
                text = " " + text
            if text.strip():
                kusy.append(((start + seg.get("tOffsetMs", 0)) / 1000, text))
    return kusy


def prepis_whisper(video, slozka):
    if not WHISPER_MODEL.exists():
        sys.exit(f"Chybí whisper model {WHISPER_MODEL} (nastav WHISPER_MODEL, modely: "
                 "https://huggingface.co/ggerganov/whisper.cpp)")
    wav = slozka / "audio.wav"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
         "-ar", "16000", "-ac", "1", str(wav)], True)
    run(["whisper-cli", "-m", str(WHISPER_MODEL), "-f", str(wav), "-l", "auto",
         "-oj", "-of", str(slozka / "whisper"), "-np"], True)
    wav.unlink()
    data = json.loads((slozka / "whisper.json").read_text(encoding="utf-8"))
    return [(s["offsets"]["from"] / 1000, " " + s["text"].strip())
            for s in data.get("transcription", []) if s["text"].strip()]


def vyber_snimky(video, slozka, interval):
    snimky = slozka / "snimky"
    if snimky.exists():
        shutil.rmtree(snimky)
    snimky.mkdir()
    if interval is None:
        sel = f"gt(scene\\,{AUTO_SCENA})+isnan(prev_selected_t)+gte(t-prev_selected_t\\,{AUTO_MAX_MEZERA})"
    else:
        sel = f"isnan(prev_selected_t)+gte(t-prev_selected_t\\,{interval})"
    r = run(["ffmpeg", "-y", "-i", str(video),
             "-vf", f"select='{sel}',scale='min(1280,iw)':-2,showinfo",
             "-fps_mode", "vfr", "-q:v", "3", str(snimky / "%04d.jpg")], True)
    casy = [float(m) for m in re.findall(r"pts_time:\s*([0-9.]+)", r.stderr)]
    soubory = sorted(snimky.glob("*.jpg"))
    vysledek = []
    for i, f in enumerate(soubory):
        t = casy[i] if i < len(casy) else 0.0
        nove = snimky / f"{i + 1:04d}_t{hms(t).replace(':', '-')}.jpg"
        f.rename(nove)
        vysledek.append((t, nove))
    return vysledek


def prehledy(slozka, snimky):
    cil = slozka / "prehledy"
    if cil.exists():
        shutil.rmtree(cil)
    if not snimky:
        return []
    cil.mkdir()
    run(["ffmpeg", "-y", "-loglevel", "error", "-pattern_type", "glob",
         "-i", str(slozka / "snimky" / "*.jpg"),
         "-vf", f"scale=320:-2,tile={PREHLED_SLOUPCE}x{PREHLED_RADKY}:padding=4:color=white",
         "-q:v", "3", str(cil / "%02d.jpg")], True)
    na_list = PREHLED_SLOUPCE * PREHLED_RADKY
    listy = sorted(cil.glob("*.jpg"))
    return [(f, snimky[i * na_list][0], snimky[min((i + 1) * na_list, len(snimky)) - 1][0],
             i * na_list + 1, min((i + 1) * na_list, len(snimky)))
            for i, f in enumerate(listy)]


def text_mezi(kusy, od, do):
    return re.sub(r"\s+", " ", "".join(t for c, t in kusy if od <= c < do)).strip()


def zapis_vystupy(slozka, meta, snimky, kusy, listy):
    hlavicka = [f"# {meta['titulek']}", "",
                f"- Zdroj: {meta['zdroj']}",
                f"- Autor: {meta.get('autor') or '—'} · délka {meta['delka']}",
                f"- Přepis: {meta['prepis']}",
                f"- Snímky: {len(snimky)} ks, hustota {meta['hustota']}",
                f"- Digitalizováno: {meta['datum']}", ""]
    if meta.get("kapitoly"):
        hlavicka += ["## Kapitoly", ""] + [f"- {hms(k['start_time'])} {k['title']}" for k in meta["kapitoly"]] + [""]
    if meta.get("popis"):
        hlavicka += ["## Popis videa", "", meta["popis"], ""]

    md = list(hlavicka)
    if listy:
        md += ["## Přehledové listy", "",
               f"Po {PREHLED_SLOUPCE}×{PREHLED_RADKY} snímcích, čtou se po řádcích zleva doprava.", ""]
        md += [f"- `prehledy/{f.name}`: snímky {a}–{b} ({hms(od)}–{hms(do)})" for f, od, do, a, b in listy]
        md += [""]
    if snimky and kusy and kusy[0][0] < snimky[0][0]:
        md += ["## Úvod (před prvním snímkem)", "", text_mezi(kusy, 0, snimky[0][0]), ""]
    for i, (t, f) in enumerate(snimky):
        konec = snimky[i + 1][0] if i + 1 < len(snimky) else float("inf")
        md += [f"## {hms(t)}", "", f"![{hms(t)}](snimky/{f.name})", ""]
        text = text_mezi(kusy, t, konec)
        if text:
            md += [text, ""]
    (slozka / "video.md").write_text("\n".join(md), encoding="utf-8")

    pr = list(hlavicka)
    if kusy:
        t = 0.0
        while t <= kusy[-1][0]:
            text = text_mezi(kusy, t, t + ODSTAVEC_S)
            if text:
                pr += [f"**[{hms(t)}]** {text}", ""]
            t += ODSTAVEC_S
    else:
        pr += ["_(bez přepisu)_"]
    (slozka / "prepis.md").write_text("\n".join(pr), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Digitalizace videa na snímky + přepis")
    ap.add_argument("zdroj", help="YouTube URL nebo cesta k videosouboru")
    ap.add_argument("--hustota", default="auto",
                    help="auto (změna scény, max 20 s mezera) | ridka 30 s | stredni 10 s | husta 3 s | <sekundy>")
    ap.add_argument("--prepis", default="auto", choices=["auto", "titulky", "whisper", "zadny"],
                    help="auto = titulky z YouTube, jinak whisper")
    ap.add_argument("--vystup", help=f"výstupní složka (výchozí {DEFAULT_ROOT}/<datum>-<název>)")
    a = ap.parse_args()

    interval = parse_hustota(a.hustota)
    lokalni = Path(a.zdroj).expanduser().exists()
    info = {} if lokalni else youtube_info(a.zdroj)
    titulek = info.get("title") or Path(a.zdroj).stem
    dnes = datetime.date.today().isoformat()
    slozka = Path(a.vystup).expanduser() if a.vystup else DEFAULT_ROOT / f"{dnes}-{slug(titulek)}"
    slozka.mkdir(parents=True, exist_ok=True)

    if lokalni:
        video = Path(a.zdroj).expanduser().resolve()
    else:
        video = slozka / "video.mp4"
        print("Stahuji video…", flush=True)
        stahni_video(a.zdroj, video)

    kusy, zdroj_prepisu = [], "žádný"
    if a.prepis in ("auto", "titulky") and not lokalni:
        jazyk, automaticke = vyber_titulky(info)
        soubor = stahni_titulky(a.zdroj, jazyk, automaticke, slozka) if jazyk else None
        if soubor:
            kusy = kusy_z_json3(soubor)
            druh = "automatické titulky" if automaticke else "titulky autora"
            zdroj_prepisu = f"YouTube {druh} ({jazyk})"
        elif a.prepis == "titulky":
            sys.exit("Titulky nejsou k dispozici (nebo YouTube stahování odmítl)")
    if not kusy and a.prepis in ("auto", "whisper"):
        print("Přepisuji zvuk whisperem…", flush=True)
        kusy = prepis_whisper(video, slozka)
        zdroj_prepisu = f"whisper ({WHISPER_MODEL.stem})"

    print("Vybírám snímky…", flush=True)
    snimky = vyber_snimky(video, slozka, interval)
    popis_hustoty = (f"auto (změna scény > {AUTO_SCENA}, max mezera {AUTO_MAX_MEZERA:g} s)"
                     if interval is None else f"1 snímek / {interval:g} s")

    delka = info.get("duration")
    meta = {"titulek": titulek, "zdroj": a.zdroj, "autor": info.get("uploader"),
            "delka": hms(delka) if delka else "?", "prepis": zdroj_prepisu,
            "hustota": popis_hustoty, "snimku": len(snimky), "datum": dnes,
            "jazyk": info.get("language"), "popis": info.get("description"),
            "kapitoly": info.get("chapters")}
    (slozka / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    zapis_vystupy(slozka, meta, snimky, kusy, prehledy(slozka, snimky))

    souhrn = {k: v for k, v in meta.items() if k not in ("popis", "kapitoly")}
    print(json.dumps({"slozka": str(slozka), **souhrn}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
