# ============================================
# MeetingMind 后端 Dockerfile
# CPU版本：适合无GPU的Docker部署
# ============================================

# 使用 Python 基础镜像
FROM python:3.11-slim

WORKDIR /app

# 创建必要的目录
RUN mkdir -p /app/uploads /app/model /app/logs

# 配置 pip 镜像
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/simple pip && \
    pip config set global.index-url https://mirrors.aliyun.com/simple && \
    pip config set global.trusted-host mirrors.aliyun.com

# 下载并安装 PyTorch CPU 版本（从 PyTorch 官方 CDN）
RUN pip install --no-cache-dir --timeout=600 \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 安装其他依赖（使用清华镜像）
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    transformers accelerate safetensors sentence-transformers==2.2.2

RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    faiss-cpu==1.7.4 FlagEmbedding==1.4.0 numpy scipy scikit-learn

RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    fastapi==0.115.0 uvicorn[standard]==0.30.6 sqlalchemy==2.0.35

RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    alembic==1.13.3 asyncpg==0.29.0 pydantic==2.9.2 pydantic-settings==2.5.2

RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    pydantic[email]==2.9.2 python-multipart==0.0.12 python-jose[cryptography]==3.3.0

RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    passlib[bcrypt]==1.7.4 loguru==0.7.2 python-dotenv==1.0.1 httpx==0.27.2 werkzeug flask jsonschema prometheus-fastapi-instrumentator prometheus-client

RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    email-validator==2.3.0 greenlet==3.1.1 redis[hiredis]==5.0.8 jieba==0.42.1

RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    fastapi-cache2==0.2.2 langchain-core==0.2.43 langgraph==0.2.76

RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    langgraph-checkpoint==2.1.2 pdfplumber==0.11.4 pypdf==5.1.0

RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    python-docx==1.1.2 openpyxl==3.1.5 openai tqdm

RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    ragas==0.2.11 aiofiles pytest pytest-asyncio pytest-cov neo4j aio-pika>=9.4.0

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]