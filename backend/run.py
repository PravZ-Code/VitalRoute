"""VitalRoute dev/prod entry point.

    python run.py               # serve on http://127.0.0.1:8000
    VR_PORT=9000 python run.py  # custom port
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app",
                host="0.0.0.0",
                port=int(os.environ.get("VR_PORT", "8000")),
                reload=os.environ.get("VR_RELOAD", "0") == "1")
