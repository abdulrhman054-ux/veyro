"""python -m veyro  ->  serve on http://127.0.0.1:8765 (local only)."""
import os

import uvicorn

if __name__ == "__main__":
    from veyro import watchdog
    watchdog.start()   # desktop app: stop when the app that started us is gone
    uvicorn.run("veyro.app:app", host="127.0.0.1", port=int(os.environ.get("VEYRO_PORT", "8765")), log_level="info")
