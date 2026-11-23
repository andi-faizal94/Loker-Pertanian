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

import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin

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


RIWAYAT_FILE = BASE / "riwayat.json"
RIWAYAT_MAKS_HARI = 90


def load_riwayat() -> list[dict]:
    if RIWAYAT_FILE.exists():
        try:
            return json.loads(RIWAYAT_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return []


def save_riwayat(riwayat: list[dict]) -> None:
    batas = (datetime.now(WIB) - timedelta(days=RIWAYAT_MAKS_HARI)).strftime("%Y-%m-%d")
    riwayat = [r for r in riwayat if r.get("tanggal", "") >= batas][-3000:]
    RIWAYAT_FILE.write_text(json.dumps(riwayat, ensure_ascii=False, indent=1), encoding="utf-8")


def tambah_riwayat(riwayat: list[dict], items: list[dict]) -> int:
    """Tambahkan loker ke arsip (tanpa duplikat). Mengembalikan jumlah yang ditambahkan."""
    ada = {r["url"] for r in riwayat}
    hari_ini = datetime.now(WIB).strftime("%Y-%m-%d")
    n = 0
    for l in items:
        if l["url"] not in ada:
            riwayat.append({**l, "tanggal": hari_ini})
            ada.add(l["url"])
            n += 1
    return n


def loker_dari_riwayat(riwayat: list[dict], hari: int) -> list[dict]:
    """Loker di arsip dalam `hari` terakhir, terbaru dulu."""
    batas = (datetime.now(WIB) - timedelta(days=hari - 1)).strftime("%Y-%m-%d")
    return sorted((r for r in riwayat if r.get("tanggal", "") >= batas), key=lambda r: r["tanggal"], reverse=True)


# ---------------------------------------------------------------- scraping
BASE_URL = "https://glints.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}


def _job_href(href: str) -> str | None:
    full = urljoin(BASE_URL, href or "").split("?")[0]
    return full if JOB_URL_RE.search(full) else None


def ambil_kartu_dari_html(html_text: str) -> list[dict]:
    """Cari semua tautan lowongan, lalu ambil teks kartu pembungkusnya."""
    soup = BeautifulSoup(html_text, "html.parser")
    by_href: dict[str, tuple] = {}
    for a in soup.select('a[href*="/opportunities/jobs/"]'):
        href = _job_href(a.get("href"))
        if not href:
            continue
        txt = a.get_text(" ", strip=True)
        if href not in by_href or (not by_href[href][1] and txt):
            by_href[href] = (a, txt)

    out = []
    for href, (a, title) in by_href.items():
        card, el = a, a
        for _ in range(10):  # naik sampai sebelum elemen yang memuat >1 lowongan
            el = el.parent
            if el is None or el.name in ("body", "html", "[document]"):
                break
            hrefs = {h for x in el.select('a[href*="/opportunities/jobs/"]') if (h := _job_href(x.get("href")))}
            if len(hrefs) > 1:
                break
            card = el
        out.append({"url": href, "title": title, "text": card.get_text("\n", strip=True)})
    return out


def _ringkas(html_text: str) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    judul = soup.title.get_text(strip=True) if soup.title else "-"
    isi = soup.get_text(" ", strip=True)[:300]
    return f"judul halaman: {judul!r} | awal isi: {isi!r}"


def scrape_dengan_requests(url: str) -> list[dict]:
    r = requests.get(url, headers=HEADERS, timeout=45)
    kartu = ambil_kartu_dari_html(r.text) if r.ok else []
    print(f"[requests] HTTP {r.status_code}, {len(kartu)} kartu")
    if not kartu:
        print(f"[requests]   {_ringkas(r.text)}")
        DEBUG_FILE.write_text(r.text, encoding="utf-8")
    return kartu


def scrape_dengan_browser(urls: list[str]) -> list[dict]:
    from playwright.sync_api import sync_playwright

    hasil = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            locale="id-ID",
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": HEADERS["Accept-Language"]},
        )
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = ctx.new_page()
        for url in urls:
            print(f"[browser] {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                try:
                    page.wait_for_selector('a[href*="/opportunities/jobs/"]', timeout=30_000)
                except Exception:  # noqa: BLE001
                    pass
                for _ in range(4):  # gulir agar kartu yang lazy-load ikut muncul
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(1500)
                html_text = page.content()
                kartu = ambil_kartu_dari_html(html_text)
                print(f"[browser]   {len(kartu)} kartu")
                if not kartu:
                    print(f"[browser]   {_ringkas(html_text)}")
                    DEBUG_FILE.write_text(html_text, encoding="utf-8")
                hasil.extend(kartu)
            except Exception as e:  # noqa: BLE001
                print(f"[browser]   GAGAL: {e}")
        browser.close()
    return hasil


def scrape_glints(urls: list[str]) -> list[dict]:
    hasil, gagal = [], []
    for url in urls:
        print(f"[scrape] {url}")
        try:
            kartu = scrape_dengan_requests(url)
        except Exception as e:  # noqa: BLE001
            print(f"[requests]   GAGAL: {e}")
            kartu = []
        (hasil.extend(kartu) if kartu else gagal.append(url))
    if gagal:
        print(f"[scrape] {len(gagal)} URL dicoba ulang dengan browser")
        try:
            hasil.extend(scrape_dengan_browser(gagal))
        except Exception as e:  # noqa: BLE001  (mis. browser belum terpasang)
            print(f"[browser] tidak bisa dipakai: {e}")
    return hasil


# ---------------------------------------------------------------- KitaLulus
KL_BASE = "https://www.kitalulus.com"
KL_DETAIL_RE = re.compile(r"/lowongan/detail/[^/?#]+")


KL_LABEL = {"dipromosikan", "lamar segera!", "baru", "urgent", "segera", "hot", "aktif merekrut"}
KL_LOKASI_RE = re.compile(r",\s*(Jawa|DI |DKI|Banten|Bali|Sumatra|Sumatera|Kalimantan|Sulawesi|Nusa|Papua|Maluku|Aceh|Riau|Lampung|Bengkulu|Jambi|Gorontalo|Kepulauan)")


def _kl_relevan(judul: str, perusahaan: str, cfg: dict) -> bool:
    """Relevan jika judulnya bertema pertanian, atau perusahaannya pertanian DAN judulnya posisi lapangan/penjualan."""
    def ada(teks, daftar):
        t = teks.lower()
        return any(re.search(rf"\b{re.escape(k.lower())}", t) for k in daftar)

    if ada(judul, cfg.get("kata_dikecualikan_judul", [])):
        return False
    if ada(judul, cfg["kata_relevan"]):
        return True
    return ada(perusahaan, cfg["kata_relevan"]) and ada(judul, cfg.get("kata_posisi_lapangan", []))


def ambil_kartu_kitalulus(html_text: str) -> list[dict]:
    """Satu kartu = satu tautan. Baris: judul, perusahaan, [label], lokasi, pendidikan, gaji, tanggal."""
    soup = BeautifulSoup(html_text, "html.parser")
    out, sudah = [], set()
    for a in soup.select('a[href*="/lowongan/detail/"]'):
        m = KL_DETAIL_RE.search(a.get("href", ""))
        if not m:
            continue
        url = KL_BASE + m.group(0)
        mentah = [l.strip() for l in a.get_text("\n", strip=True).split("\n") if l.strip()]
        if url in sudah or len(mentah) < 3 or any(l.lower() == "dipromosikan" for l in mentah):
            continue
        lines = [l for l in mentah if l.lower() not in KL_LABEL]
        judul = lines[0]
        i_lok = next((i for i, l in enumerate(lines[1:], 1) if KL_LOKASI_RE.search(l)), None)
        if i_lok is None:
            continue
        perusahaan = lines[1] if i_lok > 1 else ""
        sisa = lines[i_lok + 1:]
        sudah.add(url)
        out.append({
            "url": url,
            "title": judul,
            "perusahaan": perusahaan,
            "lokasi": lines[i_lok],
            "pendidikan": next((l for l in sisa if l.lower().startswith(("minimal", "semua jenjang"))), ""),
            "gaji": next((l for l in sisa if l.startswith("Rp") or "Dinegosiasikan" in l), "Gaji tidak ditampilkan"),
            "text": "\n".join(lines),
            "sumber": "KitaLulus",
        })
    return out


def scrape_kitalulus(cfg: dict, provinsi_list: list[str]) -> list[dict]:
    hasil = []
    for prov in cfg.get("provinsi") or provinsi_list:
        for kata in cfg["kata_kunci"]:
            url = f"{KL_BASE}/lowongan?keyword={quote_plus(kata)}&location={quote_plus(prov.lower())}"
            try:
                r = requests.get(url, headers=HEADERS, timeout=45)
                kartu = ambil_kartu_kitalulus(r.text) if r.ok else []
            except Exception as e:  # noqa: BLE001
                print(f"[kitalulus] GAGAL {prov}/{kata}: {e}")
                continue
            relevan = [k for k in kartu if _kl_relevan(k["title"], k["perusahaan"], cfg)]
            print(f"[kitalulus] {prov} / {kata}: HTTP {r.status_code}, {len(kartu)} kartu, {len(relevan)} relevan")
            hasil.extend(relevan)
            time.sleep(cfg.get("jeda_detik", 1.5))
    return hasil


# ---------------------------------------------------------------- parsing
def parse_kartu(kartu: dict, provinsi_list: list[str]) -> dict | None:
    if "lokasi" in kartu:  # kartu yang sudah diurai (KitaLulus)
        prov = next((p for p in provinsi_list if p.lower() in kartu["lokasi"].lower()), None)
        if not prov:
            return None
        return {
            "url": kartu["url"],
            "judul": kartu["title"],
            "perusahaan": kartu["perusahaan"],
            "kota": kartu["lokasi"].split(",")[0].strip(),
            "provinsi": prov,
            "gaji": kartu["gaji"],
            "pendidikan": kartu["pendidikan"],
            "sumber": kartu.get("sumber", ""),
        }
    lines = [l.strip() for l in kartu["text"].split("\n") if l.strip()]
    teks = " ".join(lines)

    teks = " ".join(lines[1:])  # jangan baca provinsi dari judul
    provinsi = next((p for p in provinsi_list if p.lower() in teks.lower()), None)
    if not provinsi:
        return None

    judul = (kartu.get("title") or "").split("\n")[0].strip()
    if not judul:
        slug = kartu["url"].rstrip("/").split("/")[-2]
        judul = slug.replace("-", " ").title()

    gaji = next(
        (l for l in lines if l.startswith("Rp") or "Gaji Tidak Ditampilkan" in l or "Dinegosiasikan" in l),
        "Gaji tidak ditampilkan",
    )
    pendidikan = next((l for l in lines if l.lower().startswith("minimal")), "")

    # lokasi & perusahaan: Glints menulis  ... Perusahaan / Kota / , / Provinsi
    perusahaan, kota = "", ""
    idx = next(i for i, l in enumerate(lines) if i > 0 and provinsi.lower() in l.lower())
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
        "sumber": kartu.get("sumber", "Glints"),
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
def susun_pesan(lowongan: list[dict], batas: int = 3500, keterangan: str | None = None) -> list[str]:
    """Pesan format HTML Telegram, dipecah agar tiap pesan < 4096 karakter."""
    e = html.escape
    tebal = lambda s: f"<b>{e(s)}</b>"  # noqa: E731
    tautan = lambda u: f'<a href="{e(u)}">Lihat &amp; lamar</a>'  # noqa: E731

    tgl = datetime.now(WIB).strftime("%d %b %Y")
    keterangan = keterangan or f"{len(lowongan)} lowongan baru"
    kepala = f"🌾 {tebal('Loker Pertanian Pulau Jawa')} — {tgl}\n{e(keterangan)}\n"

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
            blok.append(
                f"{no}. {tebal(l['judul'])}\n   {info}\n   💰 {detail}\n   🔗 {tautan(l['url'])} · {e(l.get('sumber', ''))}"
            )

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
    # ambil hanya pola token yang valid (abaikan spasi, kutip, awalan "bot", atau teks lain)
    m = re.search(r"\d{6,}:[A-Za-z0-9_-]{30,}", os.getenv("TELEGRAM_BOT_TOKEN", ""))
    tg_token = m.group(0) if m else ""
    tg_chat = re.sub(r"[^0-9,\-@A-Za-z_]", "", os.getenv("TELEGRAM_CHAT_ID", ""))
    if os.getenv("TELEGRAM_BOT_TOKEN") and not tg_token:
        print("TELEGRAM_BOT_TOKEN tidak berformat token bot (contoh: 123456789:AAH...).")
    if not dry and not (tg_token and tg_chat):
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID belum diisi.")
        return 1

    kartu = scrape_glints(CONFIG["sumber_glints"])
    kl_cfg = CONFIG.get("kitalulus", {})
    if kl_cfg.get("aktif"):
        kartu += scrape_kitalulus(kl_cfg, CONFIG["provinsi"])
    if not kartu:
        print("Tidak ada kartu lowongan terbaca. Situs mungkin berubah atau memblokir; cek debug.html.")
        return 2

    semua = [x for k in kartu if (x := parse_kartu(k, CONFIG["provinsi"]))]
    semua = saring(semua, CONFIG.get("kata_dikecualikan", []))
    seen = load_seen()
    baru = [l for l in semua if l["url"] not in set(seen)][: CONFIG.get("maks_loker_per_kirim", 30)]
    print(f"[info] {len(semua)} loker di Jawa, {len(baru)} belum pernah dikirim")

    # arsip: masukkan juga loker yang dulu sudah dikirim tapi belum tercatat di arsip
    riwayat = load_riwayat()
    sudah = set(seen)
    n_isi = tambah_riwayat(riwayat, [l for l in semua if l["url"] in sudah])
    if n_isi and not dry:
        save_riwayat(riwayat)
        print(f"[riwayat] {n_isi} loker lama ditambahkan ke arsip")

    if not baru:
        kosong = CONFIG.get("kirim_jika_kosong") or os.getenv("KIRIM_JIKA_KOSONG") == "1"
        if kosong and not dry:
            kirim_telegram(tg_token, tg_chat, "🌾 Belum ada loker pertanian baru di Pulau Jawa sejak kiriman terakhir.")
        return 0

    pesan_list = susun_pesan(baru)
    if dry:
        print("\n===== DRY RUN: pesan yang akan dikirim =====\n")
        for p in pesan_list:
            print(p, "\n-----")
        return 0

    if all([kirim_telegram(tg_token, tg_chat, p) for p in pesan_list]):
        save_seen(seen + [l["url"] for l in baru])
        tambah_riwayat(riwayat, baru)
        save_riwayat(riwayat)
        return 0
    return 3

if __name__ == "__main__":
    sys.exit(main())
