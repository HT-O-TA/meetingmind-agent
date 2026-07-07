# MeetingMind Docker 部署启动脚本
# 运行方式：powershell -ExecutionPolicy Bypass -File start-docker.ps1

Write-Host "=== MeetingMind Docker 部署脚本 ===" -ForegroundColor Cyan

# 步骤1：检查 Docker 是否运行
Write-Host "`n1. 检查 Docker 状态..." -ForegroundColor Yellow
docker info | Select-Object -First 3
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误：Docker 未运行，请先启动 Docker Desktop" -ForegroundColor Red
    exit 1
}

# 步骤2：切换到项目目录
Write-Host "`n2. 切换到项目目录..." -ForegroundColor Yellow
Set-Location "F:\project\meetingmind-agent"
Write-Host "当前目录: $(Get-Location)" -ForegroundColor Green

# 步骤3：启动 Docker Compose 服务
Write-Host "`n3. 启动 Docker Compose 服务..." -ForegroundColor Yellow
docker compose up -d

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Docker 服务启动成功！" -ForegroundColor Green
    Write-Host "`n服务访问地址：" -ForegroundColor Cyan
    Write-Host "  - 后端 API: http://localhost:8000" -ForegroundColor White
    Write-Host "  - API 文档: http://localhost:8000/docs" -ForegroundColor White
    Write-Host "  - PostgreSQL: localhost:5432" -ForegroundColor White
    Write-Host "  - Redis: localhost:6379" -ForegroundColor White
    Write-Host "  - Neo4j: http://localhost:7474" -ForegroundColor White
    
    Write-Host "`n等待服务启动..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10
    
    # 步骤4：检查服务状态
    Write-Host "`n4. 检查服务状态..." -ForegroundColor Yellow
    docker compose ps
    
    # 步骤5：检查后端健康状态
    Write-Host "`n5. 检查后端健康状态..." -ForegroundColor Yellow
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 30
        Write-Host "✅ 后端服务健康：$($response.status)" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  后端服务尚未就绪，请稍等片刻或检查日志" -ForegroundColor Yellow
    }
} else {
    Write-Host "`n❌ Docker 服务启动失败！" -ForegroundColor Red
    Write-Host "请检查错误信息并修复后重试" -ForegroundColor Yellow
}

Write-Host "`n=== 部署完成 ===" -ForegroundColor Cyan
