from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from customer_portal_api.app.bootstrap import initialize_runtime, shutdown_runtime
from customer_portal_api.app.config import settings
from customer_portal_api.app.routers.admin import router as admin_router
from customer_portal_api.app.routers.app_api import router as app_router
from customer_portal_api.app.routers.auth import router as auth_router
from customer_portal_api.app.routers.payment import router as payment_router
from i18n import CatalogError
from i18n import load as load_i18n


def _ensure_i18n_ready() -> None:
    """启动前预加载 i18n 目录；zh 缺失/损坏时中止启动 —
    Preload the i18n catalogs before startup; abort if `zh` is missing or broken.

    与桌面端 main.py 的同名守卫不同，这里不追加 PyInstaller 打包提示——portal
    以 Docker 镜像形式交付，exc 自身携带的已解析路径已经足够 —
    Unlike the desktop app's same-named guard, this does not append a
    PyInstaller bundle-file hint -- the portal ships as a Docker image, and
    exc's own message already names the resolved path.
    """
    try:
        load_i18n()
    except CatalogError as exc:
        try:
            print(str(exc))
        except Exception:
            pass
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_i18n_ready()
    initialize_runtime()
    yield
    shutdown_runtime()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api")
app.include_router(app_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(payment_router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("customer_portal_api.main:app", host="0.0.0.0", port=8100, reload=False)
