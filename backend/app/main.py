from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.plugin_two import websocket_router
from app.core.config import settings
from app.database.connection import init_database


def create_app() -> FastAPI:
    init_database()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="接收 Chrome 插件采集的岗位信息，通过 Coze Workflow 返回匹配分。",
    )
    # 开发期允许扩展页面访问；服务仅绑定本机地址，不对公网暴露。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router, prefix="/api/v1")
    app.include_router(websocket_router)
    return app


app = create_app()
