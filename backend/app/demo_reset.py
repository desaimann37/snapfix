"""`python -m app.demo_reset`: reset the running server to the demo starting state.

Calls the admin endpoint (so in-memory runtime toggles reset too); falls back to a direct reseed if the
server isn't reachable.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from app.config import get_settings


def main() -> int:
    settings = get_settings()
    url = os.environ.get("SNAPFIX_API", "http://localhost:8000") + "/api/admin/demo-reset"
    req = urllib.request.Request(url, method="POST", headers={"X-Admin-Token": settings.admin_token})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            print(json.dumps(json.loads(resp.read()), indent=2))
            return 0
    except urllib.error.HTTPError as exc:
        print(f"demo-reset failed: HTTP {exc.code} {exc.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError:
        print("API not reachable; reseeding the database directly", file=sys.stderr)
        from app.seed.generate import main as seed_main

        seed_main()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
