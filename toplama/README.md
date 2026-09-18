# toplama — Veri Toplama ve Saklama Servisi (Ingest API)

Grid Up Hackathon — İZ A (Saha ve Veri Yolu) bileşeni.

Saha gateway'lerinden veya simülatörden gelen modül paketlerini alan,
şema sözleşmesine göre doğrulayan, `alindi_zaman` damgasını ekleyip
PostgreSQL veritabanına ya da dosya sistemine yazan yüksek performanslı FastAPI servisidir.

---

## 1. Uç Noktalar (Endpoints)

- **`POST /paket`**: Modül paketini kabul eder.
  - Gövdeyi `modul_paketi.schema.json` şemasıyla doğrular. Hatalı paketlerde `400 Bad Request` döner ve reddin gerekçesini şema ihlaliyle açıklar.
  - Modülün kendi zaman damgasına dokunmaz; sunucu saatiyle `alindi_zaman` damgalar (saat kayması tespiti için bu fark zorunludur).
  - Başarılı yeni kayıtta `201 Created` ve yazılan satır sayısını döner.
  - Aynı zaman damgalı tekrar paketlerde `200 OK` ve `{"yinelenen": true}` döner (idempotent).
- **`GET /saglik`**: servis sürümü, depo durumu (`depo.durum` = `hazir` ise Docker healthcheck geçer) ve yazılan satır sayaçları (`200 OK`).

---

## 2. Kayıt Arka Uçları (Backends)

Servis `TOPLAMA_KAYIT` ortam değişkeniyle iki farklı backend ile çalışabilir:

1. **PostgreSQL (`TOPLAMA_KAYIT=postgres`) — Üretim Modu:**
   - Ölçümleri uzun/dar tabloda (`gridup.olcum`), termal kareleri ikili formatta (`gridup.termal_kare`), modül durumunu (`gridup.modul_durum`) saklar.
   - `DATABASE_URL` ile belirtilen veritabanına bağlanır.
2. **Dosya (`TOPLAMA_KAYIT=dosya`) — Test / Geliştirme Modu:**
   - Veritabanı kurulumu gerektirmeden çalışır.
   - Belirtilen dizine (`TOPLAMA_DOSYA_DIZIN`) JSONL formatında yazar (`modul.jsonl`, `olcum.jsonl`, `termal_ozet.jsonl`, `termal_kare.jsonl`, `modul_durum.jsonl`).

---

## 3. Veritabanı Migrasyonları

PostgreSQL şeması `toplama/migrations/` altındaki sıralı ve idempotent SQL dosyalarıyla kurulur:

```bash
# Sırasıyla uygulanmalıdır:
psql -d gridup -f toplama/migrations/001_sema_ve_referans.sql
psql -d gridup -f toplama/migrations/002_olcum.sql
psql -d gridup -f toplama/migrations/003_termal.sql
psql -d gridup -f toplama/migrations/004_termal_kare_ikili.sql
psql -d gridup -f toplama/migrations/005_modul_durum.sql
```

*(Not: İZ B analiz katmanı bu tabloların üzerine kendi tarama imleci ve anomali tablolarını ekler: `analiz/analiz/migrations/100_analiz.sql`; `python -m analiz sema` önce buradaki 001–005'i, sonra kendininkini uygular.)*

---

## 4. Ortam Değişkenleri

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `TOPLAMA_KAYIT` | `postgres` | Kayıt tipi: `postgres` veya `dosya` |
| `DATABASE_URL` | — (zorunlu, `postgres` modunda) | PostgreSQL bağlantı DSN'i; boşsa servis açılışta hata verir |
| `TOPLAMA_DOSYA_DIZIN` | `/veri` | Dosya modu için JSONL çıktı klasörü |
| `TOPLAMA_HOST` | `0.0.0.0` | Servisin dinleyeceği adres |
| `TOPLAMA_PORT` | `8000` | Servisin dinleyeceği port |

---

## 5. Çalıştırma

### Yerel Python Ortamında:
```bash
# Bağımlılıklar
pip install -e toplama/

# Dosya backend'i ile hızlı çalıştırma (DB gerekmez)
TOPLAMA_KAYIT=dosya TOPLAMA_DOSYA_DIZIN=/tmp/veri python -m toplama

# PostgreSQL backend'i ile çalıştırma
DATABASE_URL=postgresql://user:pass@localhost:5432/gridup python -m toplama
```

### Docker İle (On-Prem):
> **Önemli:** Build context repo kök dizini olmalıdır (çünkü `/sozlesmeler` ortak kütüphanesini içeri kopyalar):

```bash
# İmajı derleme
docker build -f toplama/Dockerfile -t gridup/toplama:1.0.0 .

# Çalıştırma
docker run --rm -p 8000:8000 \
    -e TOPLAMA_KAYIT=postgres \
    -e DATABASE_URL=postgresql://postgres:pass@db:5432/gridup \
    gridup/toplama:1.0.0
```

---

## 6. Testler

```bash
# Birim testleri (dosya modu, mock ve doğrulama)
pytest toplama/tests/

# PostgreSQL entegrasyon testlerini de koşmak için:
TEST_DATABASE_URL=postgresql:///gridup_test pytest toplama/tests/
```
