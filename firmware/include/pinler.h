// Pin atamaları — docs/track-a/03-pinout.md §3.1 ile birebir.
// Tek doğruluk kaynağı 03'tür; burada bir pin değişirse önce 03 değişir.
#pragma once

// I²C (paylaşımlı): MLX90640 0x33, SHT31 0x44 (ADDR → GND)
constexpr int PIN_SDA = 8;
constexpr int PIN_SCL = 9;
constexpr uint8_t I2C_ADRES_MLX = 0x33;
constexpr uint8_t I2C_ADRES_SHT = 0x44;
constexpr uint32_t I2C_HIZ_HZ = 400000;  // 03 §3.2: 768 değerlik kare için fast mode şart

// Akım kanalları — hepsi ADC1 (Wi-Fi aktifken ADC2 kullanılamaz, 03 §3.1)
constexpr int PIN_CT_L1 = 4;    // ADC1_CH3
constexpr int PIN_CT_L2 = 5;    // ADC1_CH4
constexpr int PIN_CT_L3 = 6;    // ADC1_CH5
constexpr int PIN_CT_N = 7;     // ADC1_CH6

// Modbus RTU hattı: UART1 ↔ MAX3485 (03 §3.3)
constexpr int PIN_UART_TX = 17;  // U1TXD → DI
constexpr int PIN_UART_RX = 18;  // U1RXD ← RO
constexpr int PIN_DE_RE = 21;    // yön: TX sırasında HIGH

// Besleme algılama: 5V_RAW (D1 öncesi) 100k/47k bölücüyle → ADC1_CH0 (03 §3.1, §3.4)
constexpr int PIN_VSENSE = 1;

// Genişleme payı (03 §3.6): boş bırakılır. GPIO10 (ADC1_CH9), GPIO11.
// Strapping pinleri GPIO0/3/45/46, USB 19/20, UART0 43/44 kullanılmaz (03 §3.1).
