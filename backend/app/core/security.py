"""安全与合规系统 - 支持权限控制、数据脱敏和审计日志"""
import re
import hashlib
from typing import Dict, List, Any, Optional, Tuple, Union
from enum import Enum
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from passlib.context import CryptContext
from jose import jwt, JWTError
from app.core.logger import app_logger
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """创建访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """解码访问令牌"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    except JWTError:
        return None


class PermissionLevel(str, Enum):
    """权限级别"""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class ResourceType(str, Enum):
    """资源类型"""
    MEETING = "meeting"
    DOCUMENT = "document"
    TODO = "todo"
    CONFIG = "config"
    TEMPLATE = "template"
    AGENT = "agent"


class AuditAction(str, Enum):
    """审计操作类型"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    LOGIN = "login"
    LOGOUT = "logout"
    PERMISSION_CHANGE = "permission_change"


class AuditStatus(str, Enum):
    """审计状态"""
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass
class AuditLog:
    """审计日志"""
    audit_id: str
    user_id: str
    action: AuditAction
    resource_type: ResourceType
    resource_id: str
    status: AuditStatus
    timestamp: datetime
    details: Dict[str, Any]
    ip_address: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class Permission:
    """权限定义"""
    permission_id: str
    user_id: str
    resource_type: ResourceType
    resource_id: str
    level: PermissionLevel
    granted_at: datetime = None
    
    def __post_init__(self):
        if self.granted_at is None:
            self.granted_at = datetime.now()


class AccessControl:
    """访问控制模块"""
    
    def __init__(self):
        self._permissions: Dict[str, List[Permission]] = {}  # user_id -> [permissions]
        self._roles: Dict[str, List[PermissionLevel]] = {}  # role -> [permissions]
    
    def grant_permission(
        self,
        user_id: str,
        resource_type: ResourceType,
        resource_id: str,
        level: PermissionLevel
    ):
        """授予权限"""
        permission = Permission(
            permission_id=f"perm_{int(datetime.now().timestamp())}",
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            level=level
        )
        
        if user_id not in self._permissions:
            self._permissions[user_id] = []
        
        # 移除旧权限（如果存在）
        self._permissions[user_id] = [
            p for p in self._permissions[user_id] 
            if not (p.resource_type == resource_type and p.resource_id == resource_id)
        ]
        
        self._permissions[user_id].append(permission)
        app_logger.info(f"[Security] 授予权限: {user_id} -> {resource_type}:{resource_id} ({level})")
    
    def revoke_permission(
        self,
        user_id: str,
        resource_type: ResourceType,
        resource_id: str
    ):
        """撤销权限"""
        if user_id not in self._permissions:
            return
        
        self._permissions[user_id] = [
            p for p in self._permissions[user_id]
            if not (p.resource_type == resource_type and p.resource_id == resource_id)
        ]
        app_logger.info(f"[Security] 撤销权限: {user_id} -> {resource_type}:{resource_id}")
    
    def check_permission(
        self,
        user_id: str,
        resource_type: ResourceType,
        resource_id: str,
        required_level: PermissionLevel
    ) -> bool:
        """检查权限"""
        if user_id not in self._permissions:
            return False
        
        permissions = self._permissions.get(user_id, [])
        
        # 检查特定资源权限
        for perm in permissions:
            if perm.resource_type == resource_type and perm.resource_id == resource_id:
                return self._has_level(perm.level, required_level)
        
        # 检查通配符权限（resource_id为*）
        for perm in permissions:
            if perm.resource_type == resource_type and perm.resource_id == "*":
                return self._has_level(perm.level, required_level)
        
        return False
    
    def _has_level(self, granted_level: PermissionLevel, required_level: PermissionLevel) -> bool:
        """检查权限级别"""
        levels = [PermissionLevel.NONE, PermissionLevel.READ, PermissionLevel.WRITE, PermissionLevel.ADMIN]
        return levels.index(granted_level) >= levels.index(required_level)
    
    def get_user_permissions(self, user_id: str) -> List[Permission]:
        """获取用户权限列表"""
        return self._permissions.get(user_id, [])
    
    def has_any_permission(self, user_id: str, resource_type: ResourceType) -> bool:
        """检查用户是否有某类资源的任何权限"""
        if user_id not in self._permissions:
            return False
        
        for perm in self._permissions[user_id]:
            if perm.resource_type == resource_type:
                return True
        
        return False


class DataMasking:
    """数据脱敏模块"""
    
    def __init__(self):
        self._patterns = {
            "phone": re.compile(r'1[3-9]\d{9}'),
            "email": re.compile(r'[\w.-]+@[\w.-]+\.\w+'),
            "id_card": re.compile(r'\d{17}[\dXx]'),
            "bank_card": re.compile(r'\d{16,19}'),
            "ip_address": re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'),
            "url": re.compile(r'https?://[\w.-]+(?:/[\w./-]*)?')
        }
    
    def mask_text(self, text: str) -> str:
        """脱敏文本"""
        result = text
        
        # 脱敏手机号
        result = self._patterns["phone"].sub(self._mask_phone, result)
        
        # 脱敏邮箱
        result = self._patterns["email"].sub(self._mask_email, result)
        
        # 脱敏身份证
        result = self._patterns["id_card"].sub(self._mask_id_card, result)
        
        # 脱敏银行卡
        result = self._patterns["bank_card"].sub(self._mask_bank_card, result)
        
        # 脱敏IP地址
        result = self._patterns["ip_address"].sub(self._mask_ip, result)
        
        return result
    
    def _mask_phone(self, match):
        """脱敏手机号"""
        phone = match.group()
        return f"{phone[:3]}****{phone[-4:]}"
    
    def _mask_email(self, match):
        """脱敏邮箱"""
        email = match.group()
        parts = email.split("@")
        if len(parts) == 2:
            username, domain = parts
            if len(username) > 2:
                return f"{username[:2]}****@{domain}"
        return "****@****.com"
    
    def _mask_id_card(self, match):
        """脱敏身份证"""
        id_card = match.group()
        return f"{id_card[:4]}**********{id_card[-4:]}"
    
    def _mask_bank_card(self, match):
        """脱敏银行卡"""
        card = match.group()
        return f"{card[:4]}********{card[-4:]}"
    
    def _mask_ip(self, match):
        """脱敏IP地址"""
        ip = match.group()
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.**.**"
        return "**.**.**.**"
    
    def mask_dict(self, data: Dict[str, Any], sensitive_fields: Optional[List[str]] = None) -> Dict[str, Any]:
        """脱敏字典数据"""
        result = {}
        sensitive_fields = sensitive_fields or ["password", "token", "secret", "key", "api_key"]
        
        for key, value in data.items():
            if key.lower() in sensitive_fields:
                result[key] = "***"
            elif isinstance(value, str):
                result[key] = self.mask_text(value)
            elif isinstance(value, dict):
                result[key] = self.mask_dict(value, sensitive_fields)
            elif isinstance(value, list):
                result[key] = [self.mask_dict(item, sensitive_fields) if isinstance(item, dict) else item for item in value]
            else:
                result[key] = value
        
        return result


class AuditLogger:
    """审计日志记录器"""
    
    def __init__(self):
        self._logs: List[AuditLog] = []
    
    def log(
        self,
        user_id: str,
        action: AuditAction,
        resource_type: ResourceType,
        resource_id: str,
        status: AuditStatus,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ):
        """记录审计日志"""
        audit_log = AuditLog(
            audit_id=f"audit_{int(datetime.now().timestamp())}_{id(self)}",
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            details=details or {},
            ip_address=ip_address,
            timestamp=datetime.now()
        )
        
        self._logs.append(audit_log)
        
        # 保持日志数量在限制范围内
        max_logs = 1000
        while len(self._logs) > max_logs:
            self._logs.pop(0)
        
        app_logger.info(f"[Audit] {user_id} {action.value} {resource_type.value}:{resource_id} [{status.value}]")
    
    def get_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        resource_type: Optional[ResourceType] = None,
        limit: int = 50
    ) -> List[AuditLog]:
        """获取审计日志"""
        logs = self._logs
        
        if user_id:
            logs = [l for l in logs if l.user_id == user_id]
        if action:
            logs = [l for l in logs if l.action == action]
        if resource_type:
            logs = [l for l in logs if l.resource_type == resource_type]
        
        return logs[-limit:]
    
    def get_summary(self) -> Dict[str, Any]:
        """获取审计摘要"""
        summary = {
            "total_logs": len(self._logs),
            "actions": {},
            "status": {"success": 0, "failure": 0}
        }
        
        for log in self._logs:
            action_key = log.action.value
            if action_key not in summary["actions"]:
                summary["actions"][action_key] = 0
            summary["actions"][action_key] += 1
            
            summary["status"][log.status.value] += 1
        
        return summary


class SecuritySystem:
    """安全与合规系统"""
    
    def __init__(self):
        self._access_control = AccessControl()
        self._data_masking = DataMasking()
        self._audit_logger = AuditLogger()
    
    def get_access_control(self) -> AccessControl:
        """获取访问控制模块"""
        return self._access_control
    
    def get_data_masking(self) -> DataMasking:
        """获取数据脱敏模块"""
        return self._data_masking
    
    def get_audit_logger(self) -> AuditLogger:
        """获取审计日志记录器"""
        return self._audit_logger
    
    def check_access(
        self,
        user_id: str,
        resource_type: ResourceType,
        resource_id: str,
        required_level: PermissionLevel
    ) -> Tuple[bool, str]:
        """检查访问权限"""
        if self._access_control.check_permission(user_id, resource_type, resource_id, required_level):
            return True, "允许访问"
        
        return False, "权限不足"
    
    def log_access(
        self,
        user_id: str,
        action: AuditAction,
        resource_type: ResourceType,
        resource_id: str,
        success: bool,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ):
        """记录访问日志"""
        status = AuditStatus.SUCCESS if success else AuditStatus.FAILURE
        self._audit_logger.log(user_id, action, resource_type, resource_id, status, details, ip_address)
    
    def sanitize_output(self, data: Any) -> Any:
        """清理输出数据（脱敏）"""
        if isinstance(data, dict):
            return self._data_masking.mask_dict(data)
        elif isinstance(data, str):
            return self._data_masking.mask_text(data)
        elif isinstance(data, list):
            return [self.sanitize_output(item) for item in data]
        return data


# 全局安全系统实例
security_system = SecuritySystem()


def get_security_system() -> SecuritySystem:
    """获取安全系统实例"""
    return security_system
