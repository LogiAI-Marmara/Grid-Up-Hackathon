// Grid-Up İZ A — pano içi modül firmware iskeleti (ESP32-S3-WROOM-1U-N8).
//
// Bu dosya modul-sim/modul_sim/modul.py'deki `Modul.ilerle()` akışının C++ karşılığıdır:
// aynı dokuz adım, aynı sırayla, aynı sabitlerle (include/ayar.h ↔ ayar.py). Simülatörde
// "dünya" ve "senaryo" sentetik olarak üretilir (adım 1–2); sahada fiziksel dünya okunur,
// o iki adım burada sensör okumasının içinde erir. Akış diyagramı: docs/track-a/07 §7.1.
//
// Politika (entegrasyon kararı madde 2, entegrasyon-gorev-dagilimi.md §2.4): her 30 sn'de
// bir paket; termal özet + 768 değerlik tam kare her pakette, koşulsuz. Modül hüküm vermez;
// pakette seviye/tip yoktur (07 §7.4).
//
// Durum: PlatformIO'da derlenir. Fiziksel modül üretilmediği için (karar kaydı §1.4) donanım
// üzerinde doğrulanmadı; sensör sürücüleri üretici kütüphaneleri, Modbus register adresleri
// ayar.h'de varsayım olarak işaretli.

#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Adafruit_MLX90640.h>
#include <Adafruit_SHT31.h>
#include <ModbusMaster.h>
#include <time.h>
#include <math.h>

#include "ayar.h"
#include "pinler.h"

// ---------------------------------------------------------------------------
// Donanım nesneleri
// ---------------------------------------------------------------------------

static Adafruit_MLX90640 termalDizi;
static Adafruit_SHT31 kabinSensoru;
static ModbusMaster modbus;

static bool termalHazir = false;
static bool kabinHazir = false;

// ---------------------------------------------------------------------------
// Modül durumu (adım 9'un girdileri)
// ---------------------------------------------------------------------------

static uint32_t cevrimSayaci = 0;          // Modul._sayac
static uint32_t arkSayaci = 0;             // Modul._ark_sayaci: TVOC-2 kümülatif trip
static uint32_t sonTvocTrip = 0;
static uint32_t yedekBaslangicMs = 0;      // 0 = şebekede
static char yazBuf[20 * 1024];             // paket JSON'u (768 değer ≈ 5–6 KB)

// ---------------------------------------------------------------------------
// Yardımcılar
// ---------------------------------------------------------------------------

static float kirp(float v, float alt, float ust) {
    return v < alt ? alt : (v > ust ? ust : v);
}

static float yuvarla2(float v) { return roundf(v * 100.0f) / 100.0f; }

// UTC ISO 8601, literal Z (sözleşme ①/②). Saat SNTP ile kurulur; kurulmadıysa false.
static bool zamanYaz(char* hedef, size_t n) {
    time_t simdi;
    time(&simdi);
    struct tm t;
    gmtime_r(&simdi, &t);
    if (t.tm_year + 1900 < 2020) return false;   // SNTP henüz gelmedi
    strftime(hedef, n, "%Y-%m-%dT%H:%M:%SZ", &t);
    return true;
}

// Modbus yön pini: MAX3485 DE/RE, TX sırasında HIGH (03 §3.3).
static void modbusOnce() { digitalWrite(PIN_DE_RE, HIGH); }
static void modbusSonra() { digitalWrite(PIN_DE_RE, LOW); }

// ---------------------------------------------------------------------------
// Adım 3 — akım: CT ön ucu (analizör yoksa) veya Modbus analizör (varsa)
// ---------------------------------------------------------------------------

// Bir CT kanalının RMS akımı. V_bias etrafında salınan burden gerilimi 100 ms boyunca
// 2 kHz'de örneklenir, ortalama (bias) çıkarılır, RMS alınır, burden ve CT oranıyla ampere çevrilir.
static float ctRmsAmper(int pin) {
    const uint32_t bitis = millis() + CT_ORNEK_SURE_MS;
    double toplam = 0.0, kareToplam = 0.0;
    uint32_t n = 0;
    while (millis() < bitis) {
        const float mv = (float)analogReadMilliVolts(pin);
        toplam += mv;
        kareToplam += (double)mv * mv;
        n++;
        delayMicroseconds(CT_ORNEK_ARALIK_US);
    }
    if (n == 0) return NAN;
    const double ort = toplam / n;
    const double varyans = kareToplam / n - ort * ort;
    const float vrms = (float)sqrt(varyans > 0 ? varyans : 0) / 1000.0f;  // V
    return vrms / R_BURDEN_OHM * CT_ORAN;
}

struct Akimlar { float l1, l2, l3, notr; bool gecerli; };

static Akimlar akimOku() {
    Akimlar a{NAN, NAN, NAN, NAN, false};
    if (ANALIZOR_VAR) {
        modbus.begin(ANALIZOR_ADRES, Serial1);
        if (modbus.readHoldingRegisters(ANALIZOR_REG_AKIM_L1, 4) == modbus.ku8MBSuccess) {
            a.l1 = modbus.getResponseBuffer(0) * ANALIZOR_AKIM_CARPAN;
            a.l2 = modbus.getResponseBuffer(1) * ANALIZOR_AKIM_CARPAN;
            a.l3 = modbus.getResponseBuffer(2) * ANALIZOR_AKIM_CARPAN;
            a.notr = modbus.getResponseBuffer(3) * ANALIZOR_AKIM_CARPAN;
            a.gecerli = true;
        }
        return a;
    }
    a.l1 = ctRmsAmper(PIN_CT_L1);
    a.l2 = ctRmsAmper(PIN_CT_L2);
    a.l3 = ctRmsAmper(PIN_CT_L3);
    a.notr = ctRmsAmper(PIN_CT_N);
    a.gecerli = !(isnan(a.l1) || isnan(a.l2) || isnan(a.l3) || isnan(a.notr));
    return a;
}

// ---------------------------------------------------------------------------
// Adım 5 — ark sayacı: TVOC-2 sayar, biz okuruz (§7.1 satır 230). Tespit yok.
// ---------------------------------------------------------------------------

static uint32_t arkTetikOku() {
    if (!TVOC2_VAR) return 0;
    modbus.begin(TVOC2_ADRES, Serial1);
    if (modbus.readHoldingRegisters(TVOC2_REG_TRIP, 1) != modbus.ku8MBSuccess) return 0;
    const uint32_t simdiki = modbus.getResponseBuffer(0);
    const uint32_t fark = simdiki >= sonTvocTrip ? simdiki - sonTvocTrip : 0;
    sonTvocTrip = simdiki;
    return fark;
}

// ---------------------------------------------------------------------------
// Adım 7 — termal: 5 alt kare ortalaması, yuvarlama özetten ÖNCE (modul.py ile aynı sebep:
// toplayıcı maks_konum'un aldığı karenin en sıcak pikselini gösterdiğini doğrular).
// ---------------------------------------------------------------------------

static float kareToplam[TERMAL_PIKSEL];
static float kare[TERMAL_PIKSEL];
static float altKare[TERMAL_PIKSEL];
static uint32_t altKareSayisi = 0;

static void termalAltKareEkle() {
    if (!termalHazir) return;
    if (termalDizi.getFrame(altKare) != 0) return;   // okuma hatası: bu alt kare atlanır
    for (int i = 0; i < TERMAL_PIKSEL; i++) kareToplam[i] += altKare[i];
    altKareSayisi++;
}

struct TermalOzet { float maks; int sutun, satir; float bolge[4]; float ortalama; };

static bool termalKareBitir(TermalOzet& o) {
    if (altKareSayisi == 0) return false;
    int maksIdx = 0;
    double toplam = 0, bolgeToplam[4] = {0, 0, 0, 0};
    int bolgeSayi[4] = {0, 0, 0, 0};
    for (int i = 0; i < TERMAL_PIKSEL; i++) {
        kare[i] = yuvarla2(kirp(kareToplam[i] / altKareSayisi, ARALIK_TERMAL_MIN, ARALIK_TERMAL_MAX));
        if (kare[i] > kare[maksIdx]) maksIdx = i;
        toplam += kare[i];
        const int c = i % TERMAL_SUTUN, s = i / TERMAL_SUTUN;
        const int b = (s < TERMAL_SATIR / 2 ? 0 : 2) + (c < TERMAL_SUTUN / 2 ? 0 : 1);  // sol-üst, sağ-üst, sol-alt, sağ-alt
        bolgeToplam[b] += kare[i];
        bolgeSayi[b]++;
    }
    o.maks = kare[maksIdx];
    o.sutun = maksIdx % TERMAL_SUTUN;
    o.satir = maksIdx / TERMAL_SUTUN;
    for (int b = 0; b < 4; b++) o.bolge[b] = yuvarla2((float)(bolgeToplam[b] / bolgeSayi[b]));
    o.ortalama = (float)(toplam / TERMAL_PIKSEL);
    return true;
}

// ---------------------------------------------------------------------------
// Adım 9 — modül sağlığı
// ---------------------------------------------------------------------------

static bool sebekedeMi() {
    const float vsense = analogReadMilliVolts(PIN_VSENSE) / 1000.0f;
    return vsense / VSENSE_BOLUCU >= SEBEKE_ESIK_V;
}

// ---------------------------------------------------------------------------
// Paket kurma — sözleşme ② JSON'u, kütüphanesiz (sabit biçim, %.2f)
// ---------------------------------------------------------------------------

struct Yazici {
    char* p; size_t kalan;
    void yaz(const char* fmt, ...) {
        va_list ap; va_start(ap, fmt);
        const int n = vsnprintf(p, kalan, fmt, ap);
        va_end(ap);
        if (n > 0 && (size_t)n < kalan) { p += n; kalan -= n; }
    }
};

static void olcumSatiri(Yazici& y, bool& ilk, const char* tip, float deger, const char* birim,
                        const char* zaman, const char* kalite) {
    y.yaz("%s{\"modul_id\":\"%s\",\"zaman\":\"%s\",\"olcum_tipi\":\"%s\",", ilk ? "" : ",", MODUL_ID, zaman, tip);
    if (strcmp(kalite, "yok") == 0) y.yaz("\"deger\":null,");   // yalnız kalite=yok null taşır
    else y.yaz("\"deger\":%.2f,", (double)deger);
    y.yaz("\"birim\":\"%s\",\"kalite\":\"%s\"}", birim, kalite);
    ilk = false;
}

// ---------------------------------------------------------------------------
// setup / loop
// ---------------------------------------------------------------------------

void setup() {
    Serial.begin(115200);
    pinMode(PIN_DE_RE, OUTPUT);
    digitalWrite(PIN_DE_RE, LOW);
    analogReadResolution(12);

    // I²C bus: MLX90640 (0x33) + SHT31 (0x44), 400 kHz (03 §3.2)
    Wire.begin(PIN_SDA, PIN_SCL, I2C_HIZ_HZ);
    kabinHazir = kabinSensoru.begin(I2C_ADRES_SHT);
    termalHazir = termalDizi.begin(I2C_ADRES_MLX, &Wire);
    if (termalHazir) {
        termalDizi.setMode(MLX90640_CHESS);
        termalDizi.setResolution(MLX90640_ADC_18BIT);
        termalDizi.setRefreshRate(MLX90640_2_HZ);
    }
    Serial.printf("sensorler: MLX90640 %s, SHT31 %s\n", termalHazir ? "ok" : "YOK", kabinHazir ? "ok" : "YOK");

    // Modbus RTU: UART1 ↔ MAX3485 (03 §3.3)
    Serial1.begin(MODBUS_BAUD, SERIAL_8N1, PIN_UART_RX, PIN_UART_TX);
    modbus.preTransmission(modbusOnce);
    modbus.postTransmission(modbusSonra);

    // Radyo: dış anten (1U), saha gateway'inin Wi-Fi'ı (§7.4)
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_SIFRE);
    for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(250);
    Serial.printf("wifi: %s\n", WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString().c_str() : "bagli degil");

    // Saat: UTC, SNTP. `zaman` modülün saatidir; toplayıcı `alindi_zaman` ekler (§11).
    configTime(0, 0, NTP_SUNUCU);
}

void loop() {
    const uint32_t cevrimBaslangic = millis();
    cevrimSayaci++;

    // ---- adım 9'un girdisi erken okunur: besleme durumu düşük güç kararını belirler ----
    const bool sebeke = sebekedeMi();
    if (sebeke) yedekBaslangicMs = 0;
    else if (yedekBaslangicMs == 0) yedekBaslangicMs = millis();
    // Süperkap gerilimi ölçülmüyor; bütçe zamanla: 3 dk yedekten sonra yalnız kalp atışı
    // (07 §7.6: "termal dizi ile radyo aynı anda karşılanamaz").
    const bool dusukGuc = !sebeke && (millis() - yedekBaslangicMs) / 1000 >= YEDEK_DUSUK_GUC_S;
    if (!sebeke) WiFi.setTxPower(WIFI_POWER_8_5dBm);   // yedekte verici kısılır (modul.py: sinyal −4 dBm)
    else WiFi.setTxPower(WIFI_POWER_19_5dBm);

    // ---- adım 1–2: dünya ve senaryo — sahada fiziksel, aşağıdaki okumaların içinde ----

    // ---- adım 3 + 7: 30 sn pencere; her 2 sn akım alt örneği, her 6 sn termal alt kare ----
    double l1 = 0, l2 = 0, l3 = 0, notr = 0;
    uint32_t akimN = 0;
    for (int i = 0; i < TERMAL_PIKSEL; i++) kareToplam[i] = 0;
    altKareSayisi = 0;

    for (uint32_t alt = 0; alt < ALT_ADIM; alt++) {
        const uint32_t altBaslangic = millis();
        if (!dusukGuc) {
            const Akimlar a = akimOku();
            if (a.gecerli) { l1 += a.l1; l2 += a.l2; l3 += a.l3; notr += a.notr; akimN++; }
            if (alt % TERMAL_HER_N_ALT_ADIM == 0) termalAltKareEkle();   // alt 0,3,6,9,12 → 5 kare
        }
        // alt adımı 2 sn'ye tamamla
        const uint32_t gecen = millis() - altBaslangic;
        if (gecen < AKIM_OKUMA_S * 1000) delay(AKIM_OKUMA_S * 1000 - gecen);
    }
    const bool akimGecerli = akimN > 0;
    if (akimGecerli) { l1 /= akimN; l2 /= akimN; l3 /= akimN; notr /= akimN; }

    // ---- adım 4: kabin havası ----
    float kabinC = NAN, kabinNem = NAN;
    if (!dusukGuc && kabinHazir) {
        kabinC = kabinSensoru.readTemperature();
        kabinNem = kabinSensoru.readHumidity();
    }

    // ---- adım 5: ark sayacı (olay bazlı, periyot yok) ----
    const uint32_t arkTetik = arkTetikOku();
    if (arkTetik) arkSayaci = min<uint32_t>(arkSayaci + arkTetik, 1000);

    // ---- adım 6: modülün saati ----
    char zaman[24];
    if (!zamanYaz(zaman, sizeof zaman)) {
        Serial.println("zaman: SNTP yok, paket atlandi");   // sözleşme `zaman` ister; uydurulmaz
        return;
    }

    // ---- adım 7 (devam): kare + özet ----
    TermalOzet ozet{};
    const bool termalVar = !dusukGuc && termalKareBitir(ozet);

    // ---- adım 8: ölçüm satırları (sözleşme ①) ----
    Yazici y{yazBuf, sizeof yazBuf};
    y.yaz("{\"modul_id\":\"%s\",\"zaman\":\"%s\",\"olcumler\":[", MODUL_ID, zaman);
    bool ilk = true;
    if (!dusukGuc) {
        const char* akimKalite = akimGecerli ? "iyi" : "yok";
        olcumSatiri(y, ilk, "akim_l1", kirp((float)l1, ARALIK_AKIM_MIN, ARALIK_AKIM_MAX), "A", zaman, akimKalite);
        olcumSatiri(y, ilk, "akim_l2", kirp((float)l2, ARALIK_AKIM_MIN, ARALIK_AKIM_MAX), "A", zaman, akimKalite);
        olcumSatiri(y, ilk, "akim_l3", kirp((float)l3, ARALIK_AKIM_MIN, ARALIK_AKIM_MAX), "A", zaman, akimKalite);
        olcumSatiri(y, ilk, "akim_notr", kirp((float)notr, ARALIK_AKIM_MIN, ARALIK_AKIM_MAX), "A", zaman, akimKalite);
        if (termalVar) {
            olcumSatiri(y, ilk, "termal_maks", ozet.maks, "C", zaman, "iyi");
            olcumSatiri(y, ilk, "termal_ort", kirp(ozet.ortalama, ARALIK_TERMAL_MIN, ARALIK_TERMAL_MAX), "C", zaman, "iyi");
        }
        if (cevrimSayaci % CEVRE_CEVRIM == 0) {   // 60 sn'de bir
            const bool kabinOk = kabinHazir && !isnan(kabinC) && !isnan(kabinNem);
            olcumSatiri(y, ilk, "ortam_sicaklik", kirp(kabinC, ARALIK_SICAKLIK_MIN, ARALIK_SICAKLIK_MAX), "C", zaman, kabinOk ? "iyi" : "yok");
            olcumSatiri(y, ilk, "nem", kirp(kabinNem, 0.0f, 100.0f), "%", zaman, kabinOk ? "iyi" : "yok");
        }
    }
    if (arkTetik) olcumSatiri(y, ilk, "ark_olay", (float)arkSayaci, "olay", zaman, "iyi");
    y.yaz("],");

    if (termalVar) {
        y.yaz("\"termal_ozet\":{\"maks\":%.2f,\"maks_konum\":[%d,%d],\"bolge_ort\":[%.2f,%.2f,%.2f,%.2f]},",
              (double)ozet.maks, ozet.sutun, ozet.satir,
              (double)ozet.bolge[0], (double)ozet.bolge[1], (double)ozet.bolge[2], (double)ozet.bolge[3]);
        y.yaz("\"termal_kare\":[");
        for (int i = 0; i < TERMAL_PIKSEL; i++) y.yaz(i ? ",%.2f" : "%.2f", (double)kare[i]);
        y.yaz("],");
    } else {
        y.yaz("\"termal_ozet\":null,\"termal_kare\":null,");
    }

    // ---- adım 9: modül sağlığı ----
    int sinyal = WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : -120;
    sinyal = sinyal < -120 ? -120 : (sinyal > 0 ? 0 : sinyal);
    y.yaz("\"modul_durum\":{\"besleme\":\"%s\",\"sinyal\":%d,\"yazilim_surumu\":\"%s\"}}",
          sebeke ? "sebeke" : "yedek", sinyal, YAZILIM_SURUMU);

    // ---- gönder: paket → saha gateway'i → toplama POST /paket (sözleşme ②) ----
    if (WiFi.status() == WL_CONNECTED) {
        HTTPClient http;
        http.begin(TOPLAMA_URL);
        http.addHeader("Content-Type", "application/json");
        const int kod = http.POST((uint8_t*)yazBuf, strlen(yazBuf));
        Serial.printf("POST /paket -> %d (%u bayt, kare %s, %s)\n", kod, (unsigned)strlen(yazBuf),
                      termalVar ? "var" : "yok", dusukGuc ? "dusuk guc" : (sebeke ? "sebeke" : "yedek"));
        http.end();
    } else {
        Serial.println("wifi yok, paket atlandi");
        WiFi.reconnect();
    }

    // çevrimi 30 sn'ye tamamla (alt adımlar zaten 30 sn tutar; pay için)
    const uint32_t gecen = millis() - cevrimBaslangic;
    if (gecen < PAKET_S * 1000) delay(PAKET_S * 1000 - gecen);
}
