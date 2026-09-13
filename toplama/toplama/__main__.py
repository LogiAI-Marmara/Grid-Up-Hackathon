"""`python -m toplama` — start the collection service.

Equivalent to `uvicorn toplama.uygulama:uygulama`, and the Dockerfile's CMD, so
there is one documented way to start the service in every environment.
"""

from __future__ import annotations

from .uygulama import main

if __name__ == "__main__":
    main()
