"""Make `modul_sim` importable when pytest is run from anywhere in the repo.

`modul-sim` has a dash in its name, so it is a folder and not a package: the
package inside it is `modul_sim`. Putting this folder on `sys.path` means
`pytest` works from the repository root, from `modul-sim/`, or from an IDE, with
no installation step — which matters because each track has to be able to run its
own tests without building the others.
"""

from __future__ import annotations

import sys
from pathlib import Path

KLASOR = Path(__file__).resolve().parent

if str(KLASOR) not in sys.path:
    sys.path.insert(0, str(KLASOR))
