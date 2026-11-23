"""
Scraper loker pertanian Pulau Jawa -> kirim ke Telegram.

Variabel lingkungan:
  TELEGRAM_BOT_TOKEN  token bot dari @BotFather
  TELEGRAM_CHAT_ID    ID chat/grup/channel tujuan, pisahkan dengan koma kalau lebih dari satu
  DRY_RUN=1           hanya tampilkan pesan di log, tidak mengirim dan tidak update seen.json
"""
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
CONFIG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
SEEN_FILE = BASE / "seen.json"
DEBUG_FILE = BASE / "debug.html"
WIB = timezone(timedelta(hours=7))

JOB_URL_RE = re.compile(r"/opportunities/jobs/[^/]+/[0-9a-f-]{36}")


# ---------------------------------------------------------------- data lama
def load_seen() -> list[str]:
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return []


def save_seen(seen: list[str]) -> None:
    SEEN_FILE.write_text(json.dumps(seen[-3000:], indent=0), encoding="utf-8")


# ---------------------------------------------------------------- scraping
JS_AMBIL_KARTU = r"""
() => {
  const isJob = h => /\/opportunities\/jobs\/[^/]+\/[0-9a-f-]{36}/.test(h);
  const byHref = new Map();
  for (const a of document.querySelectorAll('a[href*="/opportunities/jobs/"]')) {
    const href = a.href.split('?')[0];
    if (!isJob(href)) continue;
    const txt = (a.innerText || '').trim();
    if (!byHref.has(href) || (!byHref.get(href).title && txt)) byHref.set(href, {a, title: txt});
  }
  const out = [];
  for (const [href, {a, title}] of byHref) {
    // naik ke elemen pembungkus kartu: berhenti sebelum elemen yang memuat >1 lowongan
    let card = a, el = a;
    for (let i = 0; i < 10 && el.parentElement; i++) {
      el = el.parentElement;
      const hrefs = new Set([...el.querySelectorAll('a[href*="/opportunities/jobs/"]')]
        .map(x => x.href.split('?')[0]).filter(isJob));
      if (hrefs.size > 1) break;
      card = el;
    }
    out.push({url: href, title, text: card.innerText || ''});
  }
  return out;
}
"""


def scrape_glints(urls: list[str]) -> list[dict]:
    from playwright.sync_api import sync_playwright

    hasil = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            locale="id-ID",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
        )
        page = ctx.new_page()
        for url in urls:
            print(f"[scrape] {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                page.wait_for_selector('a[href*="/opportunities/jobs/"]', timeout=30_000)
                for _ in range(4):  # gulir agar kartu yang lazy-load ikut muncul
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(1500)
                kartu = page.evaluate(JS_AMBIL_KARTU)
                print(f"[scrape]   {len(kartu)} kartu ditemukan")
                hasil.extend(kartu)
            except Exception as e:  # noqa: BLE001
                print(f"[scrape]   GAGAL: {e}")
                try:
                    DEBUG_FILE.write_text(page.content(), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
        browser.close()
    return hasil


# ---------------------------------------------------------------- parsing
def parse_kartu(kartu: dict, provinsi_list: list[str]) -> dict | None:
    lines = [l.strip() for l in kartu["text"].split("\n") if l.strip()]
    teks = " ".join(lines)

    provinsi = next((p for p in provinsi_list if p.lower() in teks.lower()), None)
    if not provinsi:
        return None

    judul = kartu.get("title") or ""
    if not judul:
        slug = kartu["url"].rstrip("/").split("/")[-2]
        judul = slug.replace("-", " ").title()

    gaji = next(
        (l for l in lines if l.startswith("Rp") or "Gaji Tidak Ditampilkan" in l),
        "Gaji tidak ditampilkan",
    )
    pendidikan = next((l for l in lines if l.lower().startswith("minimal")), "")

    # lokasi & perusahaan: Glints menulis  ... Perusahaan / Kota / , / Provinsi
    perusahaan, kota = "", ""
    idx = next(i for i, l in enumerate(lines) if provinsi.lower() in l.lower())
    baris = lines[idx]
    if "," in baris and baris.split(",")[0].strip():  # "Bekasi, Jawa Barat"
        kota = baris.split(",")[0].strip()
        j = idx - 1
    else:
        j = idx - 1
        while j >= 0 and lines[j] in {",", "·", "-"}:
            j -= 1
        kota = lines[j] if j >= 0 else ""
        j -= 1
    if j >= 0 and not lines[j].startswith("+"):
        perusahaan = lines[j]

    return {
        "url": kartu["url"],
        "judul": judul,
        "perusahaan": perusahaan,
        "kota": kota,
        "provinsi": provinsi,
        "gaji": gaji,
        "pendidikan": pendidikan,
    }


def saring(lowongan: list[dict], kata_kecuali: list[str]) -> list[dict]:
    out, sudah = [], set()
    for l in lowongan:
        if l["url"] in sudah:
            continue
        gabung = f"{l['judul']} {l['perusahaan']}".lower()
        if any(k.lower() in gabung for k in kata_kecuali):
            continue
        sudah.add(l["url"])
        out.append(l)
    return out


# ---------------------------------------------------------------- susun pesan
def susun_pesan(lowongan: list[dict], batas: int = 3500) -> list[str]:
    """Pesan format HTML Telegram, dipecah agar tiap pesan < 4096 karakter."""
    e = html.escape
    tebal = lambda s: f"<b>{e(s)}</b>"  # noqa: E731
    tautan = lambda u: f'<a href="{e(u)}">Lihat &amp; lamar</a>'  # noqa: E731

    tgl = datetime.now(WIB).strftime("%d %b %Y")
    kepala = f"🌾 {tebal('Loker Pertanian Pulau Jawa')} — {tgl}\n{len(lowongan)} lowongan baru\n"

    blok = []
    per_prov: dict[str, list[dict]] = {}
    for l in lowongan:
        per_prov.setdefault(l["provinsi"], []).append(l)
    no = 0
    for prov, items in per_prov.items():
        blok.append(f"\n📍 {tebal(prov)}")
        for l in items:
            no += 1
            info = e(" · ".join(x for x in [l["perusahaan"], l["kota"]] if x))
            detail = e(" · ".join(x for x in [l["gaji"], l["pendidikan"]] if x))
            blok.append(f"{no}. {tebal(l['judul'])}\n   {info}\n   💰 {detail}\n   🔗 {tautan(l['url'])}")

    pesan, kini = [], kepala
    for b in blok:
        if len(kini) + len(b) + 1 > batas:
            pesan.append(kini)
            kini = "(lanjutan)\n"
        kini += b + "\n"
    pesan.append(kini)
    return pesan


def kirim_telegram(token: str, chat_ids: str, pesan: str) -> bool:
    ok = True
    for cid in [c.strip() for c in chat_ids.split(",") if c.strip()]:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": cid,
                "text": pesan,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=60,
        )
        try:
            j = r.json()
        except ValueError:
            j = {"ok": False, "description": r.text[:200]}
        if j.get("ok"):
            print(f"[telegram] terkirim ke {cid}")
        else:
            print(f"[telegram] GAGAL ke {cid}: {j.get('description')}")
            ok = False
    return ok


# ---------------------------------------------------------------- utama
def main() -> int:
    dry = os.getenv("DRY_RUN", "").strip() in {"1", "true", "yes"}
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not dry and not (tg_token and tg_chat):
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diisi.")
        return 1

    kartu = scrape_glints(CONFIG["sumber_glints"])
    if not kartu:
        print("Tidak ada kartu lowongan terbaca. Situs mungkin berubah atau memblokir; cek debug.html.")
        return 2

    semua = [x for k in kartu if (x := parse_kartu(k, CONFIG["provinsi"]))]
    semua = saring(semua, CONFIG.get("kata_dikecualikan", []))
    seen = load_seen()
    baru = [l for l in semua if l["url"] not in set(seen)][: CONFIG.get("maks_loker_per_kirim", 30)]
    print(f"[info] {len(semua)} loker di Jawa, {len(baru)} belum pernah dikirim")

    if not baru:
        if CONFIG.get("kirim_jika_kosong") and not dry:
            kirim_telegram(tg_token, tg_chat, "🌾 Hari ini belum ada loker pertanian baru di Pulau Jawa.")
        return 0

    pesan_list = susun_pesan(baru)
    if dry:
        print("\n===== DRY RUN: pesan yang akan dikirim =====\n")
        for p in pesan_list:
            print(p, "\n-----")
        return 0

    if all([kirim_telegram(tg_token, tg_chat, p) for p in pesan_list]):
        save_seen(seen + [l["url"] for l in baru])
        return 0
    return 3

if __name__ == "__main__":
    sys.exit(main())
