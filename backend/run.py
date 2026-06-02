import os
import uvicorn

os.environ.setdefault("PYTHONUNBUFFERED", "1")

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_config=None,
        log_level="info",
    )
