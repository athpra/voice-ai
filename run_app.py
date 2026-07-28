"""CML Application entrypoint: serves the FastAPI app on $CDSW_APP_PORT."""

import os

import nest_asyncio
import uvicorn

# CML runs Application scripts inside a Jupyter kernel, which already has an
# asyncio event loop running. uvicorn.run() calls asyncio.run() internally,
# which raises "cannot be called from a running event loop" without this patch.
nest_asyncio.apply()

if __name__ == "__main__":
    port = int(os.environ.get("CDSW_APP_PORT", os.environ.get("PORT", 8090)))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
