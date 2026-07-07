"""
Core 模块 - 应用核心组件

本包包含应用的核心基础设施组件：

| 文件 | 功能 |
|------|------|
| config.py | 配置管理 - 环境变量定义和加载 |
| config_center.py | 配置中心 - 动态配置、热更新、多源配置 |
| security.py | 安全 - JWT令牌、密码哈希、权限控制、数据脱敏 |
| logger.py | 日志 - Loguru 统一日志配置 |
| middleware.py | 中间件 - 请求访问日志 |
| exceptions.py | 异常 - 全局异常处理 |
| response.py | 响应 - 统一响应格式 |
| api_response.py | API响应 - 响应码、消息枚举、响应模型 |
| deps.py | 依赖注入 - 用户认证依赖 |
| dependencies.py | 依赖注入 - 服务实例工厂 |
| cache.py | 缓存 - 兼容层，重导出 cache_init |
| cache_init.py | 缓存初始化 - Redis/FastAPI-Cache/LLM缓存 |
| fault_tolerance.py | 容错 - 重试、降级、熔断机制 |
| observability.py | 可观测性 - 追踪、指标、监控 |
"""
