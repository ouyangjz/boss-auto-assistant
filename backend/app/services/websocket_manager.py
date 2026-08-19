import asyncio
import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger("uvicorn.error")


class PluginTwoConnectionManager:
    """管理 plugin-two 连接、待处理消息和内存 ACK 状态。"""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._pending: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._task_status: "OrderedDict[str, str]" = OrderedDict()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
            pending = list(self._pending.values())
        logger.info("[PluginTwoWS] connected clients=%s", len(self._connections))
        for payload in pending:
            try:
                await websocket.send_json(payload)
            except Exception as exc:
                logger.warning("[PluginTwoWS] failed to replay pending task: %s", exc)
                await self.disconnect(websocket)
                break

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
            count = len(self._connections)
        logger.info("[PluginTwoWS] disconnected clients=%s", count)

    async def enqueue(self, payload: Dict[str, Any]) -> None:
        task_id = str(payload.get("task_id", "")).strip()
        if not task_id:
            raise ValueError("WebSocket task payload 缺少 task_id")

        async with self._lock:
            self._pending[task_id] = payload
            self._remember_status(task_id, "pending")
            connections = list(self._connections)

        logger.info("[PluginTwoWS] pushing task %s clients=%s", task_id, len(connections))
        disconnected: List[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except Exception as exc:
                logger.warning(
                    "[PluginTwoWS] push failed task=%s error=%s", task_id, exc
                )
                disconnected.append(websocket)
        for websocket in disconnected:
            await self.disconnect(websocket)

    async def acknowledge(self, task_id: str, status: str) -> bool:
        normalized_task_id = str(task_id).strip()
        normalized_status = str(status).strip()
        if not normalized_task_id or not normalized_status:
            return False

        async with self._lock:
            existed = normalized_task_id in self._pending
            self._pending.pop(normalized_task_id, None)
            self._remember_status(normalized_task_id, normalized_status)
        logger.info(
            "[PluginTwoWS] ACK task=%s status=%s pending=%s",
            normalized_task_id,
            normalized_status,
            existed,
        )
        return existed

    async def get_task_status(self, task_id: str) -> Optional[str]:
        async with self._lock:
            return self._task_status.get(task_id)

    async def pending_count(self) -> int:
        async with self._lock:
            return len(self._pending)

    def _remember_status(self, task_id: str, status: str) -> None:
        self._task_status[task_id] = status
        self._task_status.move_to_end(task_id)
        while len(self._task_status) > 500:
            self._task_status.popitem(last=False)


plugin_two_manager = PluginTwoConnectionManager()

