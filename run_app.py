"""CML Application entrypoint: serves the FastAPI app on $CDSW_APP_PORT."""

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("CDSW_APP_PORT", os.environ.get("PORT", 8090)))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
