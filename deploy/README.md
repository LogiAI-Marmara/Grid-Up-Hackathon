# Yerel entegrasyon

Depo kökünden tek komutla bütün zinciri başlatın:

```powershell
docker compose -f deploy/docker-compose.yml up -d --build --wait
```

PowerShell için `./baslat.ps1 -Build`, Windows komut istemi için `baslat.bat`
aynı kompozisyonu başlatır. Başlatıcılar bir servis sağlıklı duruma gelmezse
hata koduyla çıkar. Arayüz `http://localhost/`, okuma API'si
`http://127.0.0.1:8080`, toplama servisi `http://127.0.0.1:8000` ve Modbus TCP
`localhost:5020` üzerindedir. PostgreSQL yalnız Docker ağı içinden
`veritabani:5432` adresiyle erişilir. Telegram değişkenleri isteğe bağlıdır;
`deploy/.env` dosyası gerekmez. Alarm imleci kalıcı `gridup_alarm_state`
volume'unda tutulur.

Entegrasyon duman testini depo kökünden çalıştırın:

```powershell
python duman_testi_kosturucu.py
```

Koşturucu kendi geçici Compose projesini ve `gridup_smoke` veritabanını kurar.
İZ A simülatöründen bir paketi toplama servisine gönderir ve İZ B okuma API'sinde
göründüğünü doğrular. Sonra İZ B'nin bilinen senaryo fikstürünü aynı test
veritabanına yazar; temiz modül, gevşek klemens, besleme kaybı ve seviye geçişi
kontrollerini `analiz.duman` ile çalıştırır. Her durumda yalnız kendi geçici
projesini ve volume'larını siler. Var olan `gridup` veritabanına bağlanmaz.

Sistemi durdurmak için:

```powershell
docker compose -f deploy/docker-compose.yml down
```
