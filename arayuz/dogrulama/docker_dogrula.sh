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

echo "==> Ağ"
docker network create "$AG" >/dev/null

echo "==> 0) Arayüz, API henüz YOKKEN ayağa kalkabilmeli"
# nginx.conf üst akışı çalışma anında çözer; sabit proxy_pass ile Nginx burada
# "host not found in upstream" diyip hiç açılmazdı (yeniden başlatma döngüsü).
docker run -d --name "$UI" --network "$AG" -p "$KONAK_PORT":80 "$IMAJ" >/dev/null
i=0
while [ "$i" -lt 30 ]; do
    if curl -fsS "http://localhost:$KONAK_PORT/index.html" >/dev/null 2>&1; then break; fi
    i=$((i + 1))
    sleep 1
done
curl -fsS "http://localhost:$KONAK_PORT/index.html" >/dev/null \
    || { echo "BAŞARISIZ: API yokken Nginx açılmadı"; docker logs "$UI" 2>&1 | tail -3; exit 1; }
KOD=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$KONAK_PORT/api/sahalar")
case "$KOD" in
    502|503|504) echo "    OK: Nginx ayakta, /api için $KOD (API yok)";;
    *) echo "BAŞARISIZ: API yokken /api/sahalar $KOD döndü, 502/503/504 beklenirdi"; exit 1;;
esac

echo "==> Sahte API"
# Sahte API: /sahalar ucuna sabit bir yanıt döndürür.
# `-w /srv` kullanılmaz: Git Bash (MSYS) `/srv`'yi Windows yoluna çevirip
# docker'a bozuk gönderir. Dizin değişimi konteyner içindeki sh'a bırakılır.
docker run -d --name "$API" --network "$AG" --network-alias "$API" \
    python:3.12-alpine sh -c \
    'mkdir -p /srv && cd /srv && printf "%s" "{\"sahalar\":[]}" > sahalar && python -m http.server 8080' >/dev/null

# Sahte API'nin hazır olmasını ve Nginx'in adı yeniden çözmesini bekle
# (resolver valid=10s; Nginx yeniden başlatılmaz).
i=0
while [ "$i" -lt 30 ]; do
    if curl -fsS "http://localhost:$KONAK_PORT/api/sahalar" >/dev/null 2>&1; then break; fi
    i=$((i + 1))
    sleep 1
done

echo "==> 1) Statik dosya"
curl -fsS "http://localhost:$KONAK_PORT/index.html" | grep -q 'id="thermal-synthetic-overlay"' \
    || { echo "BAŞARISIZ: index.html beklendiği gibi sunulmuyor"; exit 1; }
curl -fsS "http://localhost:$KONAK_PORT/app.js" | grep -q 'GridUpApp' \
    || { echo "BAŞARISIZ: app.js sunulmuyor"; exit 1; }
echo "    OK: index.html ve app.js sunuluyor"

echo "==> 2) /api vekil yolu (Nginx yeniden başlatılmadan, API sonradan geldi)"
# nginx.conf'taki `location /api/` + `rewrite ^/api/(.*)$ /$1` çifti /api önekini düşürür:
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
