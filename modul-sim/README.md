# modul-sim — Sentetik Modül Veri Üreteci ve Modül Mantığı

Grid Up Hackathon — İZ A (Saha ve Veri Yolu) bileşeni.

Pano içine yerleştirilen izleme modülünün ölçüm döngüsünü, termal dizi matrisini,
sensör davranışını ve arıza mekanizmalarını sentetik olarak simüle eden CLI aracıdır.

---

## 1. Ne Üretir?

Modül simülatörü, panodaki donanımın üreteceği paketleri **Sözleşme ② (`modul_paketi.schema.json`)**
formatında üretir. Çıktı standart `stdout` akışına yazılır (ndjson veya json dizi), çalışma
istatistikleri ise `stderr`'e basılır:

- `modul_id`: `{saha}-{pano}-{modul}` hiyerarşik kimliği (örn. `TR041-P01-M1`)
- `zaman`: ISO 8601 UTC zaman damgası
- `olcumler`: `ortam_sicaklik`, `nem`, `akim_l1`, `akim_l2`, `akim_l3`, `akim_notr`, `ark_olay`
- `termal_ozet`: `maks`, `maks_konum`, `bolge_ort` (4 bölge)
- `termal_kare`: 32×24 = 768 elemanlı sıcaklık matrisi (0,1 °C çözünürlük)
- `modul_durum`: `besleme` (`sebeke`/`yedek`), `sinyal` (dBm), `yazilim_surumu`

---

## 2. Desteklenen 7 Arıza Senaryosu

Karar kaydı §7.6 ile tanımlı tüm arıza senaryoları simüle edilebilir:

| Senaryo Adı (`--senaryo`) | Belirti | Beklenen Anomali Tipi |
|---|---|---|
| `gevsek_klemens` | Akım sabitken tek noktada (klemens) aşırı ısınma | `sicak_nokta`, `akim_sicaklik_sapmasi` |
| `asiri_yuk` | Tüm faz akımları anma değerini aşar, genel pano sıcaklığı artar | `asiri_yuk`, `ortam_sicaklik_yuksek` |
| `faz_dengesizligi` | Fazlar arası akım farkı ve nötr akımı yükselir | `faz_dengesizligi` |
| `nem_yukselmesi` | Bağıl nem yükselir, çiğ noktasına yaklaşarak yoğuşma riski doğurur | `nem_yuksek` |
| `ark_olayi` | Optik ark algılama kaydı (TVOC-2 Modbus trip sinyali) | `ark` |
| `sensor_arizasi` | Sensör donması veya gürültülü okuma (`kalite: supheli/yok`) | `sensor_arizasi` |
| `modul_sagligi` | Şebeke besleme kaybı (`yedek`), RF sinyal düşüşü, saat kayması | `modul_saglik` |

Senaryo listesini terminalden görüntülemek için:
```bash
python -m modul_sim --liste
```

---

## 3. Kurulum ve Çalıştırma

Repo kök dizininde veya `modul-sim/` dizininde:

```bash
# Bağımlılıkları yükleme
pip install -e modul-sim/

# Varsayılan normal çalışma (9 modül, 60 dk, ndjson)
python -m modul_sim

# Belirli bir arıza senaryosu ile üretim (ör. gevşek klemens)
python -m modul_sim --senaryo gevsek_klemens --modul 9 --sure 60 > veri.ndjson

# Toplama servisine doğrudan canlı borulama (pipeline)
python -m modul_sim --senaryo gevsek_klemens | while read -r paket; do
    curl -s -X POST http://localhost:8000/paket \
         -H "Content-Type: application/json" \
         -d "$paket"
done

# Sözleşme doğrulamasını zorunlu tutarak koşu
python -m modul_sim --dogrula --senaryo asiri_yuk
```

### Parametreler

- `--senaryo`: Arıza senaryosu seçimi (boş bırakılırsa normal sakin profil)
- `--modul N`: Simüle edilecek modül sayısı (Demo: 9, Yük testi: 100)
- `--sure DK`: Simülasyon penceresi uzunluğu (dakika)
- `--tohum N`: Rastgele sayı üreteci tohumu (deterministik tekrarlanabilirlik)
- `--baslangic ISO`: Simülasyon başlangıç zamanı (varsayılan: koşunun şu an bitmesini sağlayacak an)
- `--cikti`: `ndjson` (satır satır) veya `json` (tek dizi)
- `--dogrula`: Her paketi çıkışta `modul_paketi.schema.json` şemasına karşı doğrular

---

## 4. Testler

```bash
pytest modul-sim/tests/
```

Tüm senaryoların veri üretimi, fizik motorunun ısı transferi kısıtları ve sözleşme uyumluluğu
otomatik testlerle doğrulanmaktadır.

İlgili tasarım dokümantasyonu: [`docs/track-a/07-yazilim-akis.md`](../docs/track-a/07-yazilim-akis.md)
