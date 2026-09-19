// Firmware sabitleri — modul-sim/modul_sim/ayar.py ile yan yana okunur.
// Sayılar oradan alınmıştır; bir değer değişecekse iki dosya birlikte değişir.
// Karar kaydı §7.4: bunlar "merkezden modüle ayar" adayıdır, sabit değil politika.
#pragma once

#include <cstdint>

// --- Kimlik ve ağ (build_flags ile geçersiz kılınır, kaynakta sır yok) -----
#ifndef MODUL_ID
#define MODUL_ID "TR041-P01-M1"          // {saha}-{pano}-{modul}, sözleşme ②
#endif
#ifndef WIFI_SSID
#define WIFI_SSID "gridup-gateway"
#endif
#ifndef WIFI_SIFRE
#define WIFI_SIFRE "degistir"
#endif
#ifndef TOPLAMA_URL
#define TOPLAMA_URL "http://192.168.4.1:8000/paket"   // saha gateway'i → toplama servisi POST /paket
#endif
constexpr const char* YAZILIM_SURUMU = "1.0.3";       // SaglikAyar.yazilim_surumu ile aynı
constexpr const char* NTP_SUNUCU = "pool.ntp.org";    // gateway kendi NTP'sini verirse buraya

// --- Örnekleme (OrneklemeAyar, entegrasyon kararı madde 2) ---------------
constexpr uint32_t PAKET_S = 30;          // paket periyodu = akım ortalama penceresi
constexpr uint32_t AKIM_OKUMA_S = 2;      // alt örnek; 15 alt örneğin ortalaması kaydedilir
constexpr uint32_t TERMAL_OKUMA_S = 6;    // sensör 6 sn'de bir okunur, 5 alt kare ortalanır
constexpr uint32_t CEVRE_S = 60;          // ortam sıcaklık + nem: 2 çevrimde bir
constexpr uint32_t ALT_ADIM = PAKET_S / AKIM_OKUMA_S;             // 15
constexpr uint32_t TERMAL_HER_N_ALT_ADIM = TERMAL_OKUMA_S / AKIM_OKUMA_S;  // 3 → 5 alt kare
constexpr uint32_t CEVRE_CEVRIM = CEVRE_S / PAKET_S;              // 2

// --- Termal dizi (sozlesme.py) ------------------------------------------
constexpr int TERMAL_SUTUN = 32;
constexpr int TERMAL_SATIR = 24;
constexpr int TERMAL_PIKSEL = TERMAL_SUTUN * TERMAL_SATIR;  // 768

// --- Akım ön ucu (03 §3.2, eda/gen_sch.py: burden + V_bias + RC) ---------
// CT sekonderi burden üzerinde gerilim üretir; V_bias = 3V3/2 orta ray.
// Sahadaki CT'ye göre ayarlanır; bunlar başlangıç değerleridir (03 §1.4 üretim çizimi değil).
constexpr float CT_ORAN = 2000.0f;         // 2000:1 split-core (ör. 1000 A / 0,5 A)
constexpr float R_BURDEN_OHM = 33.0f;      // gen_sch notu: R_burden = 1,5 V / sekonder tepe akımı
constexpr uint32_t CT_ORNEK_SURE_MS = 100; // 5 şebeke periyodu @ 50 Hz → RMS penceresi
constexpr uint32_t CT_ORNEK_ARALIK_US = 500;  // 2 kHz örnekleme

// --- Besleme algılama (03 §3.4) -----------------------------------------
// VSENSE = 5V_RAW × 47k / (100k + 47k). RAC05 çıkışı 5 V → 1,60 V; kesintide sıfıra iner.
constexpr float VSENSE_BOLUCU = 47.0f / 147.0f;
constexpr float SEBEKE_ESIK_V = 4.0f;      // 5V_RAW bunun altındaysa "yedek"
// Süperkap gerilimi ölçülmüyor (03'te pin yok); düşük güç kararı zamanla verilir:
// 02-bom §2.5 bütçe ~5 dk @ 50 mA → 3 dk sonra yalnız kalp atışı gönder.
constexpr uint32_t YEDEK_DUSUK_GUC_S = 180;

// --- Modbus RTU (03 §3.3) ------------------------------------------------
constexpr uint32_t MODBUS_BAUD = 9600;     // 8N1
constexpr uint8_t ANALIZOR_ADRES = 1;      // panodaki analizör (varsa); slave adresi sahada ayarlanır
constexpr uint8_t TVOC2_ADRES = 2;         // ABB TVOC-2 (varsa)
constexpr bool ANALIZOR_VAR = false;       // true: akım Modbus'tan, CT okunmaz (01 §1.2 iki yol)
constexpr bool TVOC2_VAR = false;
// Analizör register haritası modele bağlıdır (Modbus RTU, 16-bit holding reg, 0,1 A çarpan varsayımı).
constexpr uint16_t ANALIZOR_REG_AKIM_L1 = 0x0000;  // L1, L2, L3, N ardışık kabul edildi
constexpr float ANALIZOR_AKIM_CARPAN = 0.1f;
// TVOC-2 Modbus kılavuzu: trip kayıtları 100–149 (03 §3.3). İlk register = trip sayacı varsayımı.
constexpr uint16_t TVOC2_REG_TRIP = 100;

// --- Sözleşme ① aralıkları (enums.OLCUM_ARALIK) — kırpma sınırları ------
constexpr float ARALIK_SICAKLIK_MIN = -40.0f, ARALIK_SICAKLIK_MAX = 150.0f;
constexpr float ARALIK_TERMAL_MIN = -40.0f, ARALIK_TERMAL_MAX = 300.0f;
constexpr float ARALIK_AKIM_MIN = 0.0f, ARALIK_AKIM_MAX = 10000.0f;
