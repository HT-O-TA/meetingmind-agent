"""认证与检索 ACL 上下文。"""
import json
from typing import Dict, List, Any, Optional
from datetime import timedelta, datetime
from dataclasses import dataclass, field
from jose import jwt, JWTError
from app.core.logger import app_logger
from app.core.config import settings
from app.core.exceptions import AppException

try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    if HAS_BCRYPT:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    else:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["pbkdf2_sha256"], default="pbkdf2_sha256")
        return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    if HAS_BCRYPT and hashed_password.startswith('$2'):
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception:
            pass
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], default="pbkdf2_sha256")
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


def user_role_value(user: Any) -> str:
    """统一处理 SQLAlchemy 字符串角色与 Enum 角色。"""
    role = getattr(user, "role", "user")
    return str(role.value if hasattr(role, "value") else role).lower()


def is_admin_user(user: Any) -> bool:
    return user_role_value(user) == "admin"


def require_write_user(user: Any) -> None:
    """只读账号不得执行业务写操作。"""
    if user_role_value(user) == "readonly":
        raise AppException("只读账号不能执行写操作", 403)


@dataclass
class AccessContext:
    """访问上下文 - 从 JWT 构造，下推到检索阶段做权限过滤

    设计目标（对应 docs/总结.md 检索记忆层）：
    将用户、部门、项目、会议、文档归属条件下推到召回阶段，
    先过滤权限再计算相关性，避免召回后过滤造成信息泄漏。

    使用方式：
        # 在 API 层从 JWT 构造
        payload = decode_access_token(token)
        ctx = AccessContext.from_jwt_payload(payload)
        # 下推到检索
        results = await bm25.search(query, access_context=ctx)
    """
    user_id: Optional[int] = None
    department: Optional[str] = None
    department_ids: List[int] = field(default_factory=list)
    project_ids: List[int] = field(default_factory=list)
    meeting_ids: List[int] = field(default_factory=list)
    document_scope: Optional[List[int]] = None  # None 表示不限制，[] 表示无权限
    is_admin: bool = False
    allow_public: bool = True
    can_write: bool = True

    @staticmethod
    def _integer_ids(values: Any) -> List[int]:
        """只保留可安全用于 SQL/Milvus 过滤表达式的整数 ID。"""
        if not isinstance(values, (list, tuple, set)):
            return []
        normalized: List[int] = []
        for value in values:
            try:
                normalized.append(int(value))
            except (TypeError, ValueError):
                app_logger.warning("[Security] 权限范围包含非整数 ID，已忽略")
        return normalized

    @staticmethod
    def _integer_id(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            app_logger.warning("[Security] 用户 ID 不是整数，已按匿名范围处理")
            return None

    @classmethod
    def from_jwt_payload(cls, payload: Dict[str, Any]) -> "AccessContext":
        """从 JWT payload 构造访问上下文"""
        return cls(
            user_id=cls._integer_id(payload.get("user_id") or payload.get("sub")),
            department=payload.get("department"),
            department_ids=cls._integer_ids(payload.get("department_ids", [])),
            project_ids=cls._integer_ids(payload.get("project_ids", [])),
            meeting_ids=cls._integer_ids(payload.get("meeting_ids", [])),
            document_scope=(
                cls._integer_ids(payload["document_scope"])
                if payload.get("document_scope") is not None
                else None
            ),
            is_admin=payload.get("is_admin", False) or payload.get("role") == "admin",
            allow_public=payload.get("allow_public", True),
            can_write=payload.get("role") != "readonly",
        )

    @classmethod
    def from_user(cls, user: Any) -> "AccessContext":
        """从已认证用户构造检索权限上下文。"""
        permissions: Dict[str, Any] = {}
        raw_permissions = getattr(user, "permissions", None)
        if raw_permissions:
            try:
                parsed = json.loads(raw_permissions)
                if isinstance(parsed, dict):
                    permissions = parsed
            except (TypeError, json.JSONDecodeError):
                app_logger.warning("[Security] 用户 permissions 不是合法 JSON 对象，忽略扩展范围")

        role = getattr(user, "role", "user")
        role_value = role.value if hasattr(role, "value") else str(role)
        return cls(
            user_id=cls._integer_id(getattr(user, "id", None)),
            department=getattr(user, "department", None),
            meeting_ids=cls._integer_ids(permissions.get("meeting_ids", [])),
            document_scope=(
                cls._integer_ids(permissions["document_scope"])
                if permissions.get("document_scope") is not None
                else None
            ),
            is_admin=role_value == "admin",
            allow_public=permissions.get("allow_public", True),
            can_write=role_value != "readonly",
        )

    def to_bm25_filters(self) -> Dict[str, Any]:
        """转换为 BM25 SQL 过滤参数（用于召回前过滤）"""
        if self.is_admin:
            return {}  # 管理员不限制
        filters = {}
        filters["user_id"] = self.user_id
        filters["department"] = self.department
        filters["allow_public"] = self.allow_public
        if self.department_ids:
            filters["department_ids"] = self.department_ids
        if self.meeting_ids:
            filters["meeting_ids"] = self.meeting_ids
        if self.document_scope is not None:
            filters["document_scope"] = self.document_scope
        return filters

    def to_milvus_expr(self) -> Optional[str]:
        """转换为 Milvus 过滤表达式（用于召回前过滤）

        Milvus expr 语法示例：
        department_id in [1, 2] and meeting_id in [10, 20]
        """
        if self.is_admin:
            return None  # 管理员不限制
        parts = []
        # 公共/上传者/部门 ACL 由 PostgreSQL 权威回查执行。Milvus 仅下推
        # 能无损表达的显式会议与文档范围，避免排除其他部门的公开文档。
        if self.meeting_ids:
            ids = ", ".join(str(m) for m in self.meeting_ids)
            parts.append(f"meeting_id in [{ids}]")
        if self.document_scope is not None and len(self.document_scope) > 0:
            ids = ", ".join(str(d) for d in self.document_scope)
            parts.append(f"document_id in [{ids}]")
        elif self.document_scope is not None and len(self.document_scope) == 0:
            parts.append("document_id in [-1]")  # 空列表 = 无权限
        return " and ".join(parts) if parts else None

    def cache_scope(self) -> Dict[str, Any]:
        """返回稳定、无敏感正文的缓存隔离范围。"""
        return {
            "user_id": self.user_id,
            "department": self.department,
            "meeting_ids": sorted(self.meeting_ids),
            "document_scope": (
                sorted(self.document_scope) if self.document_scope is not None else None
            ),
            "is_admin": self.is_admin,
            "allow_public": self.allow_public,
            "can_write": self.can_write,
        }
