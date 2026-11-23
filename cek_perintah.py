"""
Cek apakah ada perintah /loker di grup Telegram sejak pengecekan terakhir.

Kalau ada: bot langsung membalas "sedang mencari…" dan menulis ada=1 ke GITHUB_OUTPUT,
sehingga langkah berikutnya di workflow menjalankan scraper.py.
Pesan yang sudah dibaca ditandai selesai (offset) agar tidak diproses dua kali.
"""
import json
import os
import re

import requests

PERINTAH_RE = re.compile(r"^/loker(@\w+)?(\s|$)", re.IGNORECASE)


def tulis_output(ada: bool) -> None:
    out = os.getenv("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"ada={'1' if ada else '0'}\n")


def main() -> None:
    m = re.search(r"\d{6,}:[A-Za-z0-9_-]{30,}", os.getenv("TELEGRAM_BOT_TOKEN", ""))
    if not m:
        print("TELEGRAM_BOT_TOKEN belum diisi / formatnya salah.")
        tulis_output(False)
        return
    api = f"https://api.telegram.org/bot{m.group(0)}"
    chat_diizinkan = {c for c in re.sub(r"[^0-9,\-]", "", os.getenv("TELEGRAM_CHAT_ID", "")).split(",") if c}

    r = requests.get(
        f"{api}/getUpdates",
        params={"timeout": 0, "allowed_updates": json.dumps(["message"])},
        timeout=30,
    ).json()
    if not r.get("ok"):
        print(f"getUpdates gagal: {r.get('description')}")
        tulis_output(False)
        return

    updates = r.get("result", [])
    peminta: dict[str, list[str]] = {}
    for u in updates:
        msg = u.get("message") or {}
        teks = (msg.get("text") or "").strip()
        cid = str((msg.get("chat") or {}).get("id", ""))
        if PERINTAH_RE.match(teks) and cid in chat_diizinkan:
            nama = (msg.get("from") or {}).get("first_name", "seseorang")
            peminta.setdefault(cid, []).append(nama)

    # tandai semua pesan sudah dibaca
    if updates:
        requests.get(f"{api}/getUpdates", params={"offset": updates[-1]["update_id"] + 1, "timeout": 0}, timeout=30)

    print(f"[perintah] {len(updates)} pesan baru, /loker dari: {peminta or '-'}")
    for cid, nama in peminta.items():
        siapa = ", ".join(dict.fromkeys(nama))
        requests.post(
            f"{api}/sendMessage",
            json={
                "chat_id": cid,
                "text": f"⏳ Siap {siapa}, sedang mencari loker pertanian terbaru di Pulau Jawa… (1–3 menit)",
            },
            timeout=30,
        )
    tulis_output(bool(peminta))


if __name__ == "__main__":
    main()
