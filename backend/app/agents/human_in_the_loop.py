"""人机协作确认服务 - 在关键节点请求用户确认"""
import asyncio
from typing import Dict, List, Optional, Any, Callable, TypedDict
from enum import Enum
from datetime import datetime
from app.core.logger import app_logger


class ConfirmationType(str, Enum):
    """确认类型枚举"""
    PLAN_APPROVAL = "plan_approval"
    TASK_EXECUTION = "task_execution"
    TOOL_CALL = "tool_call"
    RESULT_REVIEW = "result_review"
    CRITICAL_ACTION = "critical_action"


class ConfirmationStatus(str, Enum):
    """确认状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


class ConfirmationRequest(TypedDict):
    """确认请求结构"""
    request_id: str
    type: ConfirmationType
    title: str
    message: str
    details: Dict[str, Any]
    timestamp: str
    timeout_seconds: int
    status: ConfirmationStatus
    user_response: Optional[str]


class HumanInTheLoopService:
    """人机协作服务 - 管理关键节点的用户确认请求"""
    
    def __init__(self):
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.pending_request_details: Dict[str, ConfirmationRequest] = {}
        self.pending_execution_snapshots: Dict[str, Dict[str, Any]] = {}
        self.completed_execution_snapshots: Dict[str, Dict[str, Any]] = {}
        self.request_history: List[ConfirmationRequest] = []
        self.default_timeout = 300  # 5分钟默认超时
        self._next_request_id = 0
    
    def _generate_request_id(self) -> str:
        """生成唯一请求ID"""
        self._next_request_id += 1
        return f"confirm_{self._next_request_id}_{int(datetime.now().timestamp())}"
    
    async def request_confirmation(
        self,
        confirm_type: ConfirmationType,
        title: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        resume_state: Optional[Dict[str, Any]] = None,
        timeout_seconds: Optional[int] = None,
        event_callback: Optional[Callable] = None
    ) -> bool:
        """
        请求用户确认
        
        Args:
            confirm_type: 确认类型
            title: 确认标题
            message: 确认消息
            details: 详细信息
            timeout_seconds: 超时时间（秒）
            event_callback: 事件回调函数
        
        Returns:
            True: 用户已确认
            False: 用户拒绝或超时
        """
        request_id = self._generate_request_id()
        timeout = timeout_seconds or self.default_timeout
        
        # 创建确认请求
        request: ConfirmationRequest = {
            "request_id": request_id,
            "type": confirm_type.value,
            "title": title,
            "message": message,
            "details": details or {},
            "timestamp": datetime.now().isoformat(),
            "timeout_seconds": timeout,
            "status": ConfirmationStatus.PENDING,
            "user_response": None
        }
        
        # 创建Future用于等待用户响应
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self.pending_requests[request_id] = future
        self.pending_request_details[request_id] = request
        if resume_state:
            self.pending_execution_snapshots[request_id] = resume_state
        
        # 触发确认事件
        if event_callback:
            app_logger.info(f"[HITL] 调用 event_callback 发送 confirmation_required 事件")
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
                app_logger.info(f"[HITL] event_callback 调用成功")
            except Exception as e:
                app_logger.error(f"[HITL] event_callback 调用失败: {e}")
        else:
            app_logger.error("[HITL] event_callback 为 None，无法发送确认事件！")
        
        app_logger.info(f"[HITL] 请求确认: {confirm_type.value} - {title}")
        
        try:
            # 等待用户响应或超时
            response = await asyncio.wait_for(future, timeout=timeout)
            
            if response == "approved":
                request["status"] = ConfirmationStatus.APPROVED
                request["user_response"] = "approved"
                if request_id in self.pending_execution_snapshots:
                    self.completed_execution_snapshots[request_id] = self.pending_execution_snapshots[request_id]
                app_logger.info(f"[HITL] 用户已确认: {request_id}")
                return True
            else:
                request["status"] = ConfirmationStatus.REJECTED
                request["user_response"] = response or "rejected"
                app_logger.info(f"[HITL] 用户拒绝: {request_id}")
                return False
                
        except asyncio.TimeoutError:
            request["status"] = ConfirmationStatus.TIMED_OUT
            request["user_response"] = "timeout"
            app_logger.warning(f"[HITL] 确认超时: {request_id}")
            return False
        
        finally:
            # 保存请求历史并清理
            self.request_history.append(request)
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]
            if request_id in self.pending_request_details:
                del self.pending_request_details[request_id]
            if request_id in self.pending_execution_snapshots:
                del self.pending_execution_snapshots[request_id]
    
    def respond_to_request(self, request_id: str, response: str) -> bool:
        """
        响应确认请求（由外部调用）
        
        Args:
            request_id: 请求ID
            response: 响应（approved/rejected）
        
        Returns:
            True: 响应成功
            False: 请求不存在或已处理
        """
        if request_id not in self.pending_requests:
            app_logger.warning(f"[HITL] 请求不存在或已处理: {request_id}")
            return False
        
        future = self.pending_requests[request_id]
        
        if not future.done():
            future.set_result(response)
            app_logger.info(f"[HITL] 收到响应: {request_id} -> {response}")
            return True
        
        return False
    
    def get_pending_requests(self) -> List[ConfirmationRequest]:
        """获取所有待处理的确认请求"""
        return list(self.pending_request_details.values())
    
    def get_request_history(self, limit: int = 50) -> List[ConfirmationRequest]:
        """获取确认请求历史"""
        return self.request_history[-limit:]
    
    def get_request_by_id(self, request_id: str) -> Optional[ConfirmationRequest]:
        """根据ID获取确认请求"""
        for req in self.request_history:
            if req["request_id"] == request_id:
                return req
        return self.pending_request_details.get(request_id)

    def get_resume_snapshot(self, request_id: str) -> Optional[Dict[str, Any]]:
        """获取确认点恢复快照"""
        return self.pending_execution_snapshots.get(request_id) or self.completed_execution_snapshots.get(request_id)

    def has_pending_request(self, request_id: str) -> bool:
        """确认请求是否仍在等待响应"""
        return request_id in self.pending_requests


# 全局实例
hitl_service = HumanInTheLoopService()


def get_hitl_service() -> HumanInTheLoopService:
    """获取人机协作服务实例"""
    return hitl_service
