@echo off
REM baslat.bat - Grid Up Docker Compose Tek Tık Başlatıcı
chcp 65001 > nul
echo =======================================================
echo ⚡ GRID UP - UÇTAN UCA ENTEGRE SİSTEM BAŞLATICI
echo =======================================================

set COMPOSE_FILE=%~dp0deploy\docker-compose.yml

echo 🚀 Docker Compose servisleri başlatılıyor...
docker compose -f "%COMPOSE_FILE%" up -d --build --wait
if errorlevel 1 exit /b %errorlevel%

echo.
echo 📊 Servis Durumları:
docker compose -f "%COMPOSE_FILE%" ps
if errorlevel 1 exit /b %errorlevel%

echo.
echo ✅ Sistem hazır:
echo  - Web Arayüz:  http://localhost
echo  - Okuma API:   http://localhost:8080
echo  - Toplama:     http://localhost:8000
echo  - Modbus TCP:  localhost:5020
echo =======================================================
pause
