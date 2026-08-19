import logging
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.schemas.introduction import (
    IntroductionReadyMessage,
    PluginTwoTaskResponse,
    PluginTwoTestRequest,
)
from app.services.websocket_manager import plugin_two_manager

logger = logging.getLogger("uvicorn.error")

router = APIRouter()
websocket_router = APIRouter()


def _model_dict(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


@router.post(
    "/test",
    response_model=PluginTwoTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def push_plugin_two_test(payload: PluginTwoTestRequest) -> PluginTwoTaskResponse:
    task_id = str(uuid4())
    message = IntroductionReadyMessage(
        task_id=task_id,
        company_name=payload.company_name,
        hr_name=payload.hr_name,
        hr_title=payload.hr_title,
        job_name=payload.job_name,
        match_score=payload.match_score,
        self_intro_context=[],
        greeting_message=payload.greeting_message,
        created_at=datetime.now().astimezone().replace(microsecond=0).isoformat(),
    )
    await plugin_two_manager.enqueue(_model_dict(message))
    return PluginTwoTaskResponse(success=True, task_id=task_id)


@websocket_router.websocket("/ws/plugin-two")
async def plugin_two_websocket(websocket: WebSocket) -> None:
    await plugin_two_manager.connect(websocket)
    try:
        while True:
            message = await websocket.receive_json()
            message_type = str(message.get("type", "")).strip()
            if message_type == "ack":
                valid = await plugin_two_manager.acknowledge(
                    task_id=message.get("task_id", ""),
                    status=message.get("status", ""),
                )
                if not valid:
                    logger.warning("[PluginTwoWS] invalid ACK payload=%s", message)
            elif message_type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                logger.warning("[PluginTwoWS] unsupported message type=%s", message_type)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("[PluginTwoWS] connection error: %s", exc)
    finally:
        await plugin_two_manager.disconnect(websocket)

