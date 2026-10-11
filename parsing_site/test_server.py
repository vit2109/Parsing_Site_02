"""Локальный стенд с SVG-картой и движущимися тестовыми объектами."""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from parsing_site.config import WEB_DIR

app = FastAPI(title="Тестовая карта Parsing Site")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")


@app.get("/", response_class=FileResponse)
def test_map() -> FileResponse:
    """Отдаёт автономную SVG-карту, совместимую с браузерным сборщиком."""
    return FileResponse(WEB_DIR / "test_map" / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    """Простой признак готовности для ручных и автоматических проверок."""
    return {"status": "ok"}
