# kodlar/veri_okuma/__init__.py
"""
Grid Up - Veri Okuma Paketi
Hem REST API (FastAPI Port 8080) hem de doğrudan PostgreSQL (Port 5432)
üzerinden ölçüm, durum, zaman serisi ve termal verileri okumak için
hazır sınıflar ve kolaylık fonksiyonları sunar.
"""

from .api_okuyucu import ApiOlcumOkuyucu
from .db_okuyucu import DbOlcumOkuyucu

__all__ = [
    "ApiOlcumOkuyucu",
    "DbOlcumOkuyucu",
    "son_olcumler_api",
    "son_olcumler_db"
]


def son_olcumler_api(modul_id: str, api_url: str = "http://localhost:8080") -> dict:
    """API üzerinden hızlıca bir modülün son ölçümlerini çeker."""
    okuyucu = ApiOlcumOkuyucu(api_url=api_url)
    return okuyucu.son_olcumler(modul_id)


def son_olcumler_db(modul_id: str, dsn: str = None) -> dict:
    """Veritabanından hızlıca bir modülün son ölçümlerini çeker."""
    okuyucu = DbOlcumOkuyucu(dsn=dsn)
    return okuyucu.son_olcumleri_getir(modul_id)
