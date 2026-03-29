#!/usr/bin/env python
"""Start the PDA API server.

Run from the repo root:
    python run_api.py
"""

import sys
from pathlib import Path

# Ensure pm_api is importable
sys.path.insert(0, str(Path(__file__).parent / "packages" / "pm-api" / "src"))
# Ensure pm_data_tools is importable
sys.path.insert(0, str(Path(__file__).parent / "packages" / "pm-data-tools" / "src"))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("pm_api.main:app", host="0.0.0.0", port=8000, reload=True)
