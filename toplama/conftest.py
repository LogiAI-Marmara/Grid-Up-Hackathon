"""Make `toplama` importable when pytest is run from anywhere in the repo.

The service is not installed as a package during the hackathon; it is run from
the checkout and from a container that copies the same layout. Putting this
folder on `sys.path` keeps `pytest` working from the repository root or from
`toplama/` without an editable install.
"""

from __future__ import annotations

import sys
from pathlib import Path

KLASOR = Path(__file__).resolve().parent

if str(KLASOR) not in sys.path:
    sys.path.insert(0, str(KLASOR))
