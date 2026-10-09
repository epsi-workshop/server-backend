import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .camera import camera
from .config import VERSION, config
from .correlation import correlator
from .db import SessionLocal, apply_retention, engine, init_db
from .ingest import HANDLERS, watchdog
from .journal import write_log
from .live import live
from .mqtt import bus
from .sensor_api import sensor_api
from .routers import admin, auth, control, monitoring, ws, audio


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    await live.load()
    await apply_retention(live.settings.retention_days)
    async with SessionLocal() as db:
        await admin.sync_gallery(db)  # galerie du service vision à jour même si le fichier a été perdu
    tasks = [asyncio.create_task(t) for t in (live.run(), camera.probe(), correlator.run(), watchdog())]
    if sensor_api:
        tasks.append(asyncio.create_task(sensor_api.run()))
    await write_log("info", "backend", f"Démarrage du backend {VERSION}")
    bus.start(HANDLERS)
    if not config.mqtt_enabled:
        await write_log("warn", "backend", "MQTT désactivé (MQTT_ENABLED=false) : aucune détection ni commande")
    yield
    bus.stop()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await engine.dispose()


app = FastAPI(
    title="Sentinel-X",
    version=VERSION,
    lifespan=lifespan,
    docs_url="/api/docs" if config.expose_docs else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if config.expose_docs else None,
)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def check_origin(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Anti-CSRF (en plus de SameSite=Strict) : les requêtes modifiantes doivent venir du dashboard."""
    if request.method in UNSAFE_METHODS:
        if not config.origin_allowed(request.headers.get("origin") or "", request.headers.get("host")):
            return JSONResponse(status_code=403, content={"detail": "Origine de la requête refusée."})
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Format {"detail": "message lisible"} attendu par le dashboard, au lieu de la liste brute de Pydantic."""
    err = exc.errors()[0] if exc.errors() else {"loc": (), "msg": ""}
    field = ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path"))
    where = f" ({field})" if field else ""
    return JSONResponse(status_code=422, content={"detail": f"Donnée invalide{where} : {err['msg']}"})


@app.get("/api/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


for module in (auth, monitoring, control, admin, ws, audio):
    app.include_router(module.router)
