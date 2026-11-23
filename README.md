# 🌾 Bot Loker Pertanian Pulau Jawa (Telegram)

Bot Telegram **@Loker_Anam_Bot** yang mengumpulkan lowongan kerja bidang pertanian di Pulau Jawa
(Jawa Barat, Jawa Tengah, Jawa Timur, DI Yogyakarta, Banten, DKI Jakarta) dari **Glints** dan **KitaLulus**.
Bot berjalan gratis di GitHub Actions, tanpa server.

## Cara memakai bot

Cari **@Loker_Anam_Bot** di Telegram, tekan **Start**, lalu pakai perintah:

| Perintah | Fungsi |
|---|---|
| `/loker` | loker pertanian 7 hari terakhir |
| `/riwayat 30` | loker 30 hari terakhir (angka bisa diganti, maks 90) |
| `/bantuan` | petunjuk |

Balasan bisa butuh sampai ±10 menit, karena perintah dicek setiap 10 menit.

Di grup utama, setiap pagi pukul **07:17 WIB** bot otomatis mengirim loker baru.
Perintah `/loker` di grup utama mengambil data terbaru saat itu juga, dan hanya mengirim loker yang belum pernah dikirim.

## Cara kerja

| File | Fungsi |
|---|---|
| `scraper.py` | mengambil loker dari Glints & KitaLulus, menyaring wilayah Jawa dan bidang pertanian, mengirim ke Telegram |
| `cek_perintah.py` | membaca perintah Telegram (`/loker`, `/riwayat`, `/bantuan`) |
| `config.json` | sumber, kata kunci, provinsi, kata yang dikecualikan |
| `seen.json` | daftar link loker yang sudah dikirim (agar tidak dobel) |
| `riwayat.json` | arsip loker 90 hari terakhir (untuk `/loker` di chat pribadi dan `/riwayat`) |
| `.github/workflows/loker.yml` | jadwal harian 07:17 WIB |
| `.github/workflows/perintah.yml` | cek perintah setiap 10 menit |

Token bot dan ID grup disimpan sebagai **Secrets** repo (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`), jadi tidak terlihat publik.

## Mengatur

- **Kata kunci / filter:** edit `config.json`.
  - `kitalulus.kata_kunci`: kata yang dicari di KitaLulus.
  - `kitalulus.kata_relevan`: judul harus mengandung salah satu kata ini.
  - `kitalulus.kata_dikecualikan_judul` dan `kata_dikecualikan`: judul yang dibuang.
- **Jam kirim harian:** edit `cron` di `.github/workflows/loker.yml` (waktu UTC = WIB − 7 jam).
- **Tes tanpa mengirim:** tab **Actions** → *Loker Pertanian ke Telegram* → **Run workflow** dengan centang *Tes saja*.

## Kalau ada masalah

- **Bot tidak membalas:** cek tab **Actions**. Kalau jadwal nonaktif, aktifkan lagi.
- **"Unauthorized" di log:** token bot berubah. Perbarui secret `TELEGRAM_BOT_TOKEN`.
- **"chat not found":** ID grup berubah (misalnya grup diubah menjadi supergroup). Perbarui secret `TELEGRAM_CHAT_ID`.
- **"Tidak ada kartu lowongan terbaca":** situs sumber berubah tampilan atau memblokir. Lihat log.

Ambil data secukupnya dan hormati ketentuan situs sumber. Info loker ini untuk keperluan pribadi atau komunitas.
