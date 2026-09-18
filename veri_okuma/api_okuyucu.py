# kodlar/veri_okuma/api_okuyucu.py
"""
Grid Up - REST API Veri Okuyucu
Analiz/Okuma API'si (Varsayılan: http://localhost:8080) üzerinden
ölçüm, durum, termal ve anomali verilerini okur.
"""

from __future__ import annotations
import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Any, Dict, List, Optional


class ApiOlcumOkuyucu:
    """FastAPI Okuma Servisi üzerinden veri okuma sınıfı."""

    def __init__(self, api_url: str = "http://localhost:8080", timeout: float = 5.0):
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.api_url}/{path.lstrip('/')}"
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if query:
                url = f"{url}?{query}"

        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "GridUp-VeriOkuyucu/1.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw)
                raise RuntimeError(f"API Hatası (HTTP {resp.status}): {url}")
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTP {e.code} ({url}): {err_msg}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"API'ye bağlanılamadı ({url}): {e.reason}") from e

    def saglik(self) -> Dict[str, Any]:
        """Servis sağlığı ve imleç gecikmesi bilgilerini döner."""
        return self._get("/saglik")

    def sahalar(self) -> List[Dict[str, Any]]:
        """Saha -> Pano -> Modül hiyerarşik ağacını döner."""
        return self._get("/sahalar")

    def moduller(self, saha: Optional[str] = None, durum: Optional[str] = None) -> List[Dict[str, Any]]:
        """Kayıtlı tüm modüllerin durum ve son görülme özetini döner."""
        params = {}
        if saha:
            params["saha"] = saha
        if durum:
            params["durum"] = durum
        yanit = self._get("/moduller", params)
        if isinstance(yanit, dict):
            if "veriler" in yanit:
                return yanit["veriler"]
            if "moduller" in yanit:
                return yanit["moduller"]
        elif isinstance(yanit, list):
            return yanit
        return []

    def modul_detay(self, modul_id: str) -> Dict[str, Any]:
        """Modülün tüm detaylarını, sinyal, besleme ve son ölçümlerini döner."""
        return self._get(f"/moduller/{urllib.parse.quote(modul_id)}")

    def son_olcumler(self, modul_id: str) -> Dict[str, float]:
        """
        Modüle ait en son ölçüm değerlerini okur ve
        {ölçüm_tipi: değer} sözlüğü olarak sadeleştirip döner.
        Örnek: {'akim_l1': 98.4, 'ortam_sicaklik': 28.1, 'nem': 44.0}
        """
        detay = self.modul_detay(modul_id)
        ham_olcumler = detay.get("son_olcumler", [])
        sonuclar = {}
        for item in ham_olcumler:
            tip = item.get("olcum_tipi")
            deger = item.get("deger")
            if tip is not None and deger is not None:
                sonuclar[tip] = deger
        return sonuclar

    def zaman_serisi(
        self,
        modul_id: str,
        olcum_tipi: str,
        bas: Optional[str] = None,
        bit: Optional[str] = None,
        aralik: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Belirli bir modül ve ölçüm tipi için geçmiş zaman serisini çeker.
        bas, bit: ISO 8601 string örn. '2026-09-18T00:00:00Z'
        aralik: saniye cinsinden kovalama/downsampling periyodu
        """
        params = {"tip": olcum_tipi}
        if bas:
            params["bas"] = bas
        if bit:
            params["bit"] = bit
        if aralik:
            params["aralik"] = aralik
        return self._get(f"/moduller/{urllib.parse.quote(modul_id)}/seri", params)

    def termal_son(self, modul_id: str) -> Dict[str, Any]:
        """Modüle ait son termal özet verisini (maks, konum, bölge ortalamaları) döner."""
        return self._get(f"/moduller/{urllib.parse.quote(modul_id)}/termal/son")

    def termal_kare(self, kare_id: str) -> Dict[str, Any]:
        """
        Kare ID'ye göre tam termal piksel matrisini (32x24 = 768 değer) döner.
        """
        return self._get(f"/termal/kare/{urllib.parse.quote(kare_id)}")

    def anomaliler(
        self,
        modul_id: Optional[str] = None,
        seviye: Optional[str] = None,
        durum: Optional[str] = "acik"
    ) -> List[Dict[str, Any]]:
        """Anomali listesini filtreleyerek döner."""
        params = {}
        if modul_id:
            params["modul"] = modul_id
        if seviye:
            params["seviye"] = seviye
        if durum:
            params["durum"] = durum
        yanit = self._get("/anomaliler", params)
        if isinstance(yanit, dict) and "anomaliler" in yanit:
            return yanit["anomaliler"]
        elif isinstance(yanit, list):
            return yanit
        return yanit
