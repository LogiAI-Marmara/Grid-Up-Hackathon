# baslat.ps1
# Grid Up Hackathon - Tüm Sistem Docker Compose Başlatıcı (PowerShell)
param(
    [switch]$Build = $false,
    [switch]$Durdur = $false
)

$Dizin = Split-Path -Parent $MyInvocation.MyCommand.Path
$ComposeDosyasi = Join-Path $Dizin "deploy\docker-compose.yml"

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "⚡ GRID UP - UÇTAN UCA ENTEGRE SİSTEM BAŞLATICI" -ForegroundColor Yellow
Write-Host "=======================================================" -ForegroundColor Cyan

if ($Durdur) {
    Write-Host "🛑 Servisler durduruluyor..." -ForegroundColor Yellow
    docker compose -f $ComposeDosyasi down
    exit 0
}

Write-Host "🚀 Docker Compose servisleri ayağa kaldırılıyor..." -ForegroundColor Green
if ($Build) {
    docker compose -f $ComposeDosyasi up -d --build
} else {
    docker compose -f $ComposeDosyasi up -d
}

Write-Host "`n📊 Servis Durumları:" -ForegroundColor Cyan
docker compose -f $ComposeDosyasi ps

Write-Host "`n✅ Erişim Noktaları:" -ForegroundColor Green
Write-Host " - Web İzleme Arayüzü: http://localhost" -ForegroundColor White
Write-Host " - Okuma API (FastAPI): http://localhost:8080" -ForegroundColor White
Write-Host " - Toplama Servisi:     http://localhost:8000" -ForegroundColor White
Write-Host " - SCADA Modbus TCP:    localhost:5020" -ForegroundColor White
Write-Host " - PostgreSQL Deposu:   localhost:5432 (db: gridup)" -ForegroundColor White
Write-Host "=======================================================" -ForegroundColor Cyan
