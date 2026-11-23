# Bot Loker Pertanian Pulau Jawa → Telegram

Setiap pagi (07:17 WIB) bot ini mengambil lowongan kategori Pertanian dari Glints,
menyaring yang berlokasi di Pulau Jawa (Jabar, Jateng, Jatim, DIY, Banten, DKI),
lalu mengirim lowongan **yang belum pernah dikirim** ke Telegram Anda.
Bot berjalan di GitHub Actions dan semuanya gratis: tidak perlu server, tidak ada biaya.

Yang dibutuhkan: akun **GitHub** dan akun **Telegram**.

---

## 1. Buat bot Telegram (±5 menit)
1. Di Telegram, cari **@BotFather** → kirim `/newbot`.
2. Isi nama bot (bebas), lalu username yang berakhiran `bot`, misalnya `lokertani_jawa_bot`.
3. BotFather memberi **token** seperti `7712345678:AAH...`. Simpan token ini dan jangan dibagikan.

## 2. Cari chat ID tujuan
Pilih ke mana loker akan dikirim:
- **Chat pribadi:** buka bot Anda, tekan **Start**, kirim pesan apa saja.
- **Grup:** masukkan bot ke grup, lalu kirim satu pesan di grup.
- **Channel:** jadikan bot admin channel, lalu kirim satu postingan.

Setelah itu buka di browser (ganti `<TOKEN>` dengan token Anda):

    https://api.telegram.org/bot<TOKEN>/getUpdates

Cari bagian `"chat":{"id": ... }`. Angka itulah **chat ID**.
ID grup/channel biasanya diawali tanda minus, misalnya `-1001234567890`.
Kalau hasilnya kosong (`"result":[]`), kirim satu pesan lagi lalu muat ulang halaman.

## 3. Buat repository GitHub
1. Di github.com klik **New repository**, beri nama misalnya `loker-tani`.
   Sebaiknya pilih **Private**.
2. Ekstrak zip, lalu upload semua isinya (termasuk folder `.github`) ke repository itu.
   Cara termudah: **Add file → Upload files**, lalu seret semua file dan folder.

## 4. Simpan token sebagai *secret*
Repository → **Settings → Secrets and variables → Actions → New repository secret**:

| Name                 | Isi                                                   |
|----------------------|-------------------------------------------------------|
| `TELEGRAM_BOT_TOKEN` | token dari BotFather                                  |
| `TELEGRAM_CHAT_ID`   | chat ID tujuan (beberapa tujuan dipisah koma)         |

## 5. Tes dulu
1. Tab **Actions** → pilih **Loker Pertanian ke Telegram** → **Run workflow**.
2. Biarkan centang **Tes saja** aktif → **Run**.
3. Buka hasil run, lalu klik langkah *Scrape & kirim*. Pesan yang *akan* dikirim tampil di log.
4. Kalau isinya sudah benar, jalankan lagi dengan centang **Tes saja** dimatikan.
   Pesan akan masuk ke Telegram.

Setelah itu bot berjalan otomatis setiap pagi.

---

## Pengaturan (`config.json`)
| Kunci                  | Fungsi                                                                 |
|------------------------|------------------------------------------------------------------------|
| `sumber_glints`        | daftar URL halaman Glints yang diambil (bisa ditambah URL kategori/pencarian lain) |
| `provinsi`             | provinsi yang diterima; hapus yang tidak diinginkan                    |
| `kata_dikecualikan`    | lowongan yang judul/perusahaannya mengandung kata ini dibuang          |
| `maks_loker_per_kirim` | batas jumlah loker per hari                                            |
| `kirim_jika_kosong`    | `true` = tetap kirim pesan "belum ada loker baru"                      |

Untuk mengubah jam kirim, edit baris `cron` di `.github/workflows/loker.yml`.
Waktunya dalam UTC (WIB − 7 jam), misalnya `"0 23 * * *"` berarti 06:00 WIB.

## Kalau ada masalah
- **"Tidak ada kartu lowongan terbaca"**: Glints mungkin mengubah tampilan atau memblokir akses.
  Unduh artefak `debug` dari halaman run untuk melihat halaman yang diterima.
- **"chat not found"**: chat ID salah, atau Anda belum menekan Start di bot
  (atau bot belum dimasukkan ke grup/channel).
- **"bot was blocked by the user"**: buka bot, lalu tekan Start lagi.
- **"Unauthorized"**: token bot salah. Salin ulang dari @BotFather.
- **Jadwal berhenti sendiri**: GitHub menonaktifkan jadwal di repo yang lama tidak ada aktivitas.
  Buka tab Actions, lalu aktifkan kembali.
- `seen.json` menyimpan daftar loker yang sudah dikirim, jadi jangan dihapus
  (kecuali ingin semua loker dikirim ulang).

## Catatan
Ambil data secukupnya: sekali sehari sudah cukup. Hormati ketentuan situs sumber,
dan pakai hasilnya untuk keperluan pribadi atau komunitas, bukan untuk diterbitkan ulang secara massal.
