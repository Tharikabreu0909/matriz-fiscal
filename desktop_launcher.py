from __future__ import annotations

from threading import Timer
import webbrowser

import uvicorn


def open_browser() -> None:
    webbrowser.open("http://127.0.0.1:8141")


if __name__ == "__main__":
    Timer(1.2, open_browser).start()
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8141,
        access_log=False,
    )
