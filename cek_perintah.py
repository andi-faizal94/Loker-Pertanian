"""
Cek perintah Telegram yang masuk sejak pengecekan terakhir (dijalankan GitHub Actions tiap 10 menit).

Di grup utama (TELEGRAM_CHAT_ID):
  /loker          -> balas "sedang mencari…", lalu workflow menjalankan scraper.py (ada=1)
  /riwayat [hari] -> kirim loker dari arsip
Di chat pribadi dengan bot (dan grup lain):
  /start, /bantuan -> petunjuk
  /loker           -> loker 7 hari terakhir dari arsip
  /riwayat [hari]  -> loker N hari terakhir dari arsip (maks 90)
"""
import json
import os
import re
import time

import requests

from scraper import load_riwayat, loker_dari_riwayat, susun_pesan

PERINTAH_RE = re.compile(r"^/(\w+)(@\w+)?(?:\s+(.*))?$", re.IGNORECASE | re.DOTALL)
MAKS_TAMPIL = 60
HARI_DEFAULT = 7
HARI_MAKS = 90

BANTUAN = (
    "🌾 <b>Bot Loker Pertanian Pulau Jawa</b>\n\n"
    "Perintah yang bisa dipakai:\n"
    "/loker – loker 7 hari terakhir\n"
    "/riwayat 30 – loker 30 hari terakhir (angka bisa diganti, maks 90)\n"
    "/bantuan – tampilkan petunjuk ini\n\n"
    "Sumber: Glints &amp; KitaLulus, wilayah Jabar, Jateng, Jatim, DIY, Banten, DKI.\n"
    "⏱️ Balasan bisa butuh sampai ±10 menit."
)


def tulis_output(ada: bool) -> None:
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"ada={'1' if ada else '0'}\n")


class Bot:
    def __init__(self, token: str):
        self.api = f"https://api.telegram.org/bot{token}"

    def kirim(self, chat_id, teks: str) -> None:
        r = requests.post(
            f"{self.api}/sendMessage",
            json={"chat_id": chat_id, "text": teks, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=30,
        )
        try:
            ok = r.json().get("ok")
        except ValueError:
            ok = False
        if not ok:
            print(f"[kirim] gagal ke {chat_id}: {r.text[:200]}")
        time.sleep(1)  # batas Telegram ±1 pesan/detik per chat


def kirim_arsip(bot: Bot, chat_id, hari: int) -> None:
    hari = max(1, min(hari, HARI_MAKS))
    items = loker_dari_riwayat(load_riwayat(), hari)
    if not items:
        bot.kirim(chat_id, f"📭 Belum ada loker di arsip untuk {hari} hari terakhir. Coba lagi besok pagi ya.")
        return
    ket = f"{len(items)} lowongan dalam {hari} hari terakhir"
    if len(items) > MAKS_TAMPIL:
        ket += f" (ditampilkan {MAKS_TAMPIL} terbaru)"
    for teks in susun_pesan(items[:MAKS_TAMPIL], keterangan=ket):
        bot.kirim(chat_id, teks)


def baca_hari(arg: str | None) -> int:
    m = re.search(r"\d+", arg or "")
    return int(m.group(0)) if m else HARI_DEFAULT


def main() -> None:
    m = re.search(r"\d{6,}:[A-Za-z0-9_-]{30,}", os.getenv("TELEGRAM_BOT_TOKEN", ""))
    if not m:
        print("TELEGRAM_BOT_TOKEN belum diisi / formatnya salah.")
        tulis_output(False)
        return
    bot = Bot(m.group(0))
    grup_utama = {c for c in re.sub(r"[^0-9,\-]", "", os.getenv("TELEGRAM_CHAT_ID", "")).split(",") if c}

    r = requests.get(
        f"{bot.api}/getUpdates",
        params={"timeout": 0, "allowed_updates": json.dumps(["message"])},
        timeout=30,
    ).json()
    if not r.get("ok"):
        print(f"getUpdates gagal: {r.get('description')}")
        tulis_output(False)
        return
    updates = r.get("result", [])

    # tandai semua pesan sudah dibaca, sebelum diproses (agar tidak dibalas dua kali bila ada error)
    if updates:
        requests.get(f"{bot.api}/getUpdates", params={"offset": updates[-1]["update_id"] + 1, "timeout": 0}, timeout=30)

    scrape_untuk: dict[str, list[str]] = {}
    sudah_dibalas: set[tuple] = set()
    for u in updates:
        msg = u.get("message") or {}
        chat = msg.get("chat") or {}
        cid = str(chat.get("id", ""))
        pribadi = chat.get("type") == "private"
        teks = (msg.get("text") or "").strip()
        nama = (msg.get("from") or {}).get("first_name", "")
        pm = PERINTAH_RE.match(teks)
        perintah = pm.group(1).lower() if pm else None
        arg = pm.group(3) if pm else None

        if perintah == "loker" and cid in grup_utama:
            scrape_untuk.setdefault(cid, []).append(nama or "seseorang")
            continue

        kunci = (cid, perintah, arg)
        if kunci in sudah_dibalas:
            continue
        sudah_dibalas.add(kunci)

        if perintah == "loker":
            print(f"[perintah] /loker (arsip) dari {cid}")
            kirim_arsip(bot, cid, HARI_DEFAULT)
        elif perintah == "riwayat":
            print(f"[perintah] /riwayat {arg or ''} dari {cid}")
            kirim_arsip(bot, cid, baca_hari(arg))
        elif perintah in ("start", "bantuan", "help") or (pribadi and teks):
            if (cid, "bantuan") not in sudah_dibalas:
                sudah_dibalas.add((cid, "bantuan"))
                bot.kirim(cid, BANTUAN)

    print(f"[perintah] {len(updates)} pesan baru, /loker grup dari: {scrape_untuk or '-'}")
    for cid, nama in scrape_untuk.items():
        siapa = ", ".join(dict.fromkeys(nama))
        bot.kirim(cid, f"⏳ Siap {siapa}, sedang mencari loker pertanian terbaru di Pulau Jawa… (1–3 menit)")
    tulis_output(bool(scrape_untuk))


if __name__ == "__main__":
    main()
