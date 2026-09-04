"""人机协作确认服务 - 异步事件驱动模式（使用Redis持久化）"""
import json
import uuid
import time
from typing import Dict, List, Optional, Any, Callable, TypedDict
from enum import Enum
from datetime import datetime
from app.core.logger import app_logger
from app.core.cache_init import get_redis
from app.core.config import settings


class ConfirmationType(str, Enum):
    PLAN_APPROVAL = "plan_approval"
    TASK_EXECUTION = "task_execution"
    TOOL_CALL = "tool_call"
    RESULT_REVIEW = "result_review"
    CRITICAL_ACTION = "critical_action"


class ConfirmationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


class ConfirmationRequest(TypedDict):
    request_id: str
    type: str
    title: str
    message: str
    details: Dict[str, Any]
    timestamp: str
    timeout_seconds: int
    status: str
    user_response: Optional[str]
    thread_id: Optional[str]
    checkpoint_key: Optional[str]
    run_status: str
    claim_token: Optional[str]
    claimed_until: Optional[float]
    attempt_count: int
    last_error: Optional[str]


class HumanInTheLoopService:
    
    def __init__(self):
        self.redis = None
        self.default_timeout = 300
        self._pending_requests: Dict[str, ConfirmationRequest] = {}
        self._request_callbacks: Dict[str, Callable] = {}
    
    async def _get_redis(self):
        if self.redis is None:
            self.redis = get_redis()
        return self.redis
    
    def _generate_request_id(self) -> str:
        return f"confirm_{uuid.uuid4().hex[:12]}_{int(datetime.now().timestamp())}"
    
    def _get_request_key(self, request_id: str) -> str:
        return f"hitl:request:{request_id}"
    
    def _get_thread_request_key(self, thread_id: str) -> str:
        return f"hitl:thread:{thread_id}"
    
    async def request_confirmation(
        self,
        confirm_type: ConfirmationType,
        title: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        resume_state: Optional[Dict[str, Any]] = None,
        timeout_seconds: Optional[int] = None,
        event_callback: Optional[Callable] = None,
        thread_id: Optional[str] = None,
    ) -> str:
        """
        请求用户确认（异步模式）
        
        Returns:
            request_id: 确认请求ID，用于后续查询状态
        """
        request_id = self._generate_request_id()
        timeout = timeout_seconds or self.default_timeout
        
        request: ConfirmationRequest = {
            "request_id": request_id,
            "type": confirm_type.value,
            "title": title,
            "message": message,
            "details": details or {},
            "timestamp": datetime.now().isoformat(),
            "timeout_seconds": timeout,
            "status": ConfirmationStatus.PENDING.value,
            "user_response": None,
            "thread_id": thread_id,
            "checkpoint_key": None,
            "run_status": "pending",
            "claim_token": None,
            "claimed_until": None,
            "attempt_count": 0,
            "last_error": None,
        }
        
        if resume_state:
            checkpoint_key = f"hitl:checkpoint:{request_id}"
            request["checkpoint_key"] = checkpoint_key
            redis = await self._get_redis()
            await redis.set(checkpoint_key, json.dumps(resume_state), ex=timeout + 60)
        
        redis = await self._get_redis()
        await redis.set(self._get_request_key(request_id), json.dumps(request), ex=timeout + 60)
        
        if thread_id:
            await redis.set(self._get_thread_request_key(thread_id), request_id, ex=timeout + 60)
        
        self._pending_requests[request_id] = request
        if event_callback:
            self._request_callbacks[request_id] = event_callback
        
        app_logger.info(f"[HITL] 请求确认: {confirm_type.value} - {title} (request_id: {request_id})")
        
        if event_callback:
            try:
                await event_callback("confirmation_required", {
                    "request_id": request_id,
                    "type": confirm_type.value,
                    "title": title,
                    "message": message,
                    "details": details,
                    "timestamp": request["timestamp"],
                    "timeout_seconds": timeout
                })
            except Exception as e:
                app_logger.error(f"[HITL] event_callback 调用失败: {e}")
        
        return request_id
    
    @staticmethod
    def _owned_by(request: ConfirmationRequest, expected_user_id: Optional[int]) -> bool:
        if expected_user_id is None:
            return True
        owner = (request.get("details") or {}).get("user_id")
        return owner is not None and str(owner) == str(expected_user_id)

    async def respond_to_request(
        self,
        request_id: str,
        response: str,
        expected_user_id: Optional[int] = None,
    ) -> bool:
        """响应确认请求"""
        redis = await self._get_redis()
        request_key = self._get_request_key(request_id)
        
        request_data = await redis.get(request_key)
        if not request_data:
            app_logger.warning(f"[HITL] 请求不存在或已过期: {request_id}")
            return False
        
        request: ConfirmationRequest = json.loads(request_data)

        if not self._owned_by(request, expected_user_id):
            app_logger.warning("[HITL] 用户无权响应确认请求: %s", request_id)
            return False
        
        if request["status"] != ConfirmationStatus.PENDING.value:
            app_logger.warning(f"[HITL] 请求已处理: {request_id}")
            return False
        
        request["status"] = ConfirmationStatus.APPROVED.value if response == "approved" else ConfirmationStatus.REJECTED.value
        request["user_response"] = response
        
        await redis.set(request_key, json.dumps(request), ex=3600)
        
        if request["thread_id"]:
            await redis.delete(self._get_thread_request_key(request["thread_id"]))
        
        if request_id in self._pending_requests:
            del self._pending_requests[request_id]
        
        callback = self._request_callbacks.get(request_id)
        if callback:
            try:
                await callback("confirmation_received", {
                    "request_id": request_id,
                    "status": request["status"],
                    "response": response
                })
            except Exception as e:
                app_logger.error(f"[HITL] 回调执行失败: {e}")
            del self._request_callbacks[request_id]
        
        app_logger.info(f"[HITL] 收到响应: {request_id} -> {response}")
        return True

    async def claim_request(
        self,
        request_id: str,
        expected_user_id: Optional[int] = None,
        lease_seconds: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Atomically claim an approved confirmation for execution.

        The short Redis NX lock closes the double-click race.  An expired lease
        can be claimed again, allowing a worker crash to recover automatically.
        """
        redis = await self._get_redis()
        request_key = self._get_request_key(request_id)
        request_data = await redis.get(request_key)
        if not request_data:
            return None
        request = json.loads(request_data)
        if not self._owned_by(request, expected_user_id):
            return None
        if request.get("status") not in {
            ConfirmationStatus.PENDING.value,
            ConfirmationStatus.APPROVED.value,
        }:
            return None
        now = time.time()
        claimed_until = float(request.get("claimed_until") or 0)
        if request.get("run_status") == "running" and claimed_until > now:
            return None
        lease = int(lease_seconds or settings.AGENT_CHECKPOINT_CLAIM_LEASE_SECONDS)
        lock_key = f"hitl:claim:{request_id}"
        token = uuid.uuid4().hex
        locked = await redis.set(lock_key, token, ex=lease, nx=True)
        if not locked:
            return None
        request["status"] = ConfirmationStatus.APPROVED.value
        request["user_response"] = "approved"
        request["run_status"] = "running"
        request["claim_token"] = token
        request["claimed_until"] = now + lease
        request["attempt_count"] = int(request.get("attempt_count") or 0) + 1
        await redis.set(request_key, json.dumps(request), ex=max(3600, lease + 60))
        return request

    async def finish_claim(
        self,
        request_id: str,
        claim_token: str,
        *,
        success: bool,
        error: Optional[str] = None,
    ) -> bool:
        """Complete or release a claimed run; failures remain retryable."""
        redis = await self._get_redis()
        request_key = self._get_request_key(request_id)
        request_data = await redis.get(request_key)
        if not request_data:
            return False
        request = json.loads(request_data)
        if request.get("run_status") != "running" or request.get("claim_token") != claim_token:
            return False
        request["run_status"] = "succeeded" if success else "failed"
        request["last_error"] = (error or "")[:2000] if error else None
        request["claimed_until"] = None
        request["claim_token"] = None
        await redis.set(request_key, json.dumps(request), ex=3600)
        await redis.delete(f"hitl:claim:{request_id}")
        return True
    
    async def get_request_status(
        self,
        request_id: str,
        expected_user_id: Optional[int] = None,
    ) -> Optional[ConfirmationRequest]:
        """获取确认请求状态"""
        redis = await self._get_redis()
        request_data = await redis.get(self._get_request_key(request_id))
        if request_data:
            request = json.loads(request_data)
            return request if self._owned_by(request, expected_user_id) else None
        return None
    
    async def get_request_by_thread_id(self, thread_id: str) -> Optional[ConfirmationRequest]:
        """根据线程ID获取确认请求"""
        redis = await self._get_redis()
        request_id = await redis.get(self._get_thread_request_key(thread_id))
        if request_id:
            return await self.get_request_status(request_id)
        return None
    
    async def get_resume_state(
        self,
        request_id: str,
        expected_user_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """获取恢复状态"""
        request = await self.get_request_status(request_id, expected_user_id)
        if request and request.get("checkpoint_key"):
            redis = await self._get_redis()
            checkpoint_data = await redis.get(request["checkpoint_key"])
            if checkpoint_data:
                return json.loads(checkpoint_data)
        return None

    async def update_resume_state(
        self,
        request_id: str,
        resume_state: Dict[str, Any],
        expected_user_id: Optional[int] = None,
    ) -> bool:
        """Refresh the cached snapshot after the definitive request ID exists."""
        request = await self.get_request_status(request_id, expected_user_id)
        if not request or not request.get("checkpoint_key"):
            return False
        redis = await self._get_redis()
        await redis.set(
            request["checkpoint_key"],
            json.dumps(resume_state),
            ex=int(request.get("timeout_seconds") or self.default_timeout) + 60,
        )
        return True
    
    async def list_pending_requests(
        self, expected_user_id: Optional[int] = None
    ) -> List[ConfirmationRequest]:
        """获取所有待处理请求"""
        redis = await self._get_redis()
        pattern = "hitl:request:*"
        requests = []
        
        async for key in redis.scan_iter(match=pattern):
            request_data = await redis.get(key)
            if request_data:
                request = json.loads(request_data)
                if (
                    (
                        request["status"] == ConfirmationStatus.PENDING.value
                        or request.get("run_status") == "failed"
                    )
                    and self._owned_by(request, expected_user_id)
                ):
                    requests.append(request)
        
        return requests

    async def list_request_history(
        self, limit: int = 50, expected_user_id: Optional[int] = None
    ) -> List[ConfirmationRequest]:
        """列出已处理请求，最近的请求优先。"""
        redis = await self._get_redis()
        requests = []

        async for key in redis.scan_iter(match="hitl:request:*"):
            request_data = await redis.get(key)
            if not request_data:
                continue
            request = json.loads(request_data)
            if (
                request["status"] != ConfirmationStatus.PENDING.value
                and self._owned_by(request, expected_user_id)
            ):
                requests.append(request)

        requests.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        return requests[:limit]
    
    async def cancel_request(self, request_id: str) -> bool:
        """取消确认请求"""
        request = await self.get_request_status(request_id)
        if not request:
            return False
        
        request["status"] = ConfirmationStatus.REJECTED.value
        redis = await self._get_redis()
        await redis.set(self._get_request_key(request_id), json.dumps(request), ex=3600)
        
        if request["thread_id"]:
            await redis.delete(self._get_thread_request_key(request["thread_id"]))

        self._pending_requests.pop(request_id, None)
        self._request_callbacks.pop(request_id, None)
        
        app_logger.info(f"[HITL] 请求已取消: {request_id}")
        return True


hitl_service = HumanInTheLoopService()


def get_hitl_service() -> HumanInTheLoopService:
    return hitl_service
