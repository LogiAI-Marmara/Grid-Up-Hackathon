#!/usr/bin/env sh
# Grid Up — İZ C arayüzü: Docker/Nginx doğrulaması
#
# Ne yapar:
#   1. arayuz/Dockerfile ile imajı kurar.
#   2. Sahte bir API konteyneri (analiz_api adıyla) ayağa kaldırır; nginx.conf
#      vekil hedefi tam olarak bu ada bakar.
#   3. Statik dosyanın ve /api/... vekil yolunun doğru sunulduğunu doğrular.
#
# Koşturma (repo kökünden):
#   sh arayuz/dogrulama/docker_dogrula.sh
#
# Çıkış kodu 0 ise her iki yol da doğrulanmıştır.
set -eu

AG=gridup_arayuz_dogrulama
IMAJ=gridup-arayuz:dogrulama
API=analiz_api
UI=gridup_arayuz_test
KONAK_PORT=${KONAK_PORT:-18080}
KOK=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

temizle() {
    docker rm -f "$UI" "$API" >/dev/null 2>&1 || true
    docker network rm "$AG" >/dev/null 2>&1 || true
}
trap temizle EXIT
temizle

echo "==> İmaj kuruluyor"
docker build -t "$IMAJ" "$KOK"

echo "==> Ağ ve sahte API"
docker network create "$AG" >/dev/null

# Sahte API: /sahalar ucuna sabit bir yanıt döndürür.
docker run -d --name "$API" --network "$AG" --network-alias "$API" \
    -w /srv python:3.12-alpine sh -c \
    'mkdir -p /srv && printf "%s" "{\"sahalar\":[]}" > /srv/sahalar && python -m http.server 8080' >/dev/null

echo "==> Arayüz konteyneri"
docker run -d --name "$UI" --network "$AG" -p "$KONAK_PORT":80 "$IMAJ" >/dev/null

# Nginx ve sahte API'nin hazır olmasını bekle
i=0
while [ "$i" -lt 30 ]; do
    if curl -fsS "http://localhost:$KONAK_PORT/index.html" >/dev/null 2>&1; then break; fi
    i=$((i + 1))
    sleep 1
done

echo "==> 1) Statik dosya"
curl -fsS "http://localhost:$KONAK_PORT/index.html" | grep -q 'id="thermal-synthetic-overlay"' \
    || { echo "BAŞARISIZ: index.html beklendiği gibi sunulmuyor"; exit 1; }
curl -fsS "http://localhost:$KONAK_PORT/app.js" | grep -q 'GridUpApp' \
    || { echo "BAŞARISIZ: app.js sunulmuyor"; exit 1; }
echo "    OK: index.html ve app.js sunuluyor"

echo "==> 2) /api vekil yolu"
# nginx.conf'taki `location /api/` + `proxy_pass .../` çifti /api önekini düşürür:
# /api/sahalar  ->  http://analiz_api:8080/sahalar
GOVDE=$(curl -fsS "http://localhost:$KONAK_PORT/api/sahalar")
echo "$GOVDE" | grep -q 'sahalar' \
    || { echo "BAŞARISIZ: /api/sahalar vekil yanıtı beklendiği gibi değil: $GOVDE"; exit 1; }
echo "    OK: /api/sahalar -> $API:8080/sahalar"

echo "==> 3) nginx.conf web kökünde YAYIMLANMAMALI"
# try_files bulunamayan yolu /index.html'e düşürdüğü için HTTP durumuna değil,
# gövdenin yapılandırma içerip içermediğine bakılır.
CONF_GOVDE=$(curl -fsS "http://localhost:$KONAK_PORT/nginx.conf" 2>/dev/null || true)
if printf "%s" "$CONF_GOVDE" | grep -q 'proxy_pass'; then
    echo "BAŞARISIZ: nginx.conf tarayıcıya sunuluyor (.dockerignore eksik)"; exit 1
fi
echo "    OK: yapılandırma dosyaları yayımlanmıyor"

echo
echo "TÜMÜ GEÇTİ — imaj, statik sunum ve /api vekil yolu doğrulandı."
