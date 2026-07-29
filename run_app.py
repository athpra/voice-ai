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
    # Bound to loopback rather than 0.0.0.0: on this workspace, something else
    # was already holding 0.0.0.0:$CDSW_APP_PORT at container start, causing
    # every deploy to fail with "address already in use" regardless of
    # subdomain/pod. Binding to 127.0.0.1 avoided that conflict, and CML's
    # own proxy still reaches the app fine (confirmed against a live external
    # request) -- so this is a real fix for this workspace, not just a
    # workaround masking the crash.
    uvicorn.run("app.main:app", host="127.0.0.1", port=port)
