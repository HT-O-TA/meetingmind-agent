import sys
import logging
from loguru import logger
from app.core.config import settings


class InterceptHandler(logging.Handler):
    """将 Python 标准 logging 路由到 loguru，使 uvicorn 日志也通过 loguru 输出"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


class VectorFilter:
    """过滤器：移除包含向量数据的日志"""
    
    @staticmethod
    def should_filter(message: str) -> bool:
        """检查消息是否应该被过滤"""
        # 过滤包含向量数组的日志
        if 'embedding_array' in message.lower():
            return True
        # 过滤包含大量数字（可能是向量）的日志
        if '[' in message and ']' in message:
            # 检查是否包含连续的浮点数（向量的典型特征）
            import re
            # 匹配类似 [-0.123, 0.456, ...] 的模式
            if re.search(r'\[\s*-?\d+\.\d+', message):
                return True
        return False


def setup_logger():
    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # 添加过滤器，过滤包含向量数据的日志
    logger.add(
        sys.stdout, 
        format=log_format, 
        level=settings.LOG_LEVEL, 
        colorize=True,
        filter=lambda record: not VectorFilter.should_filter(record["message"])
    )

    # 拦截所有标准 logging（uvicorn、sqlalchemy 等），统一通过 loguru 输出
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in list(logging.root.manager.loggerDict.keys()):
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False

    return logger


app_logger = setup_logger()