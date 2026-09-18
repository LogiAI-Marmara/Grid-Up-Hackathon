# kodlar/veri_oku.py
"""
Grid Up - Pratik Ölçüm Verisi Okuma Başlatıcısı
Doğrudan `python kodlar/veri_oku.py` olarak çalıştırılabilir.
"""

import sys
import os

# Mevcut dizini sys.path'e ekle
simdiki_dizin = os.path.dirname(os.path.abspath(__file__))
if simdiki_dizin not in sys.path:
    sys.path.insert(0, simdiki_dizin)

from veri_okuma.cli import calistir

if __name__ == "__main__":
    sys.exit(calistir())
