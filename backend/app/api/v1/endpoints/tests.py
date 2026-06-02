"""测试API端点 - 提供测试结果展示接口"""
import subprocess
import json
from typing import Dict, Any
from fastapi import APIRouter

router = APIRouter(tags=["Tests"])


@router.get("/run-unit-tests")
async def run_unit_tests():
    """运行单元测试并返回结果"""
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/unit/", "-v", "--tb=short", "-q"],
        cwd="f:/project/meetingmind/backend",
        capture_output=True,
        text=True,
        timeout=120
    )
    
    output = result.stdout
    error = result.stderr
    return_code = result.returncode
    
    # 解析测试结果
    tests_run = 0
    tests_passed = 0
    tests_failed = 0
    duration = "0s"
    
    lines = output.split("\n")
    for line in lines:
        if "passed" in line and "failed" in line:
            # 提取测试数量
            parts = line.split()
            for part in parts:
                if part.isdigit():
                    tests_run += int(part)
                if "passed" in line.lower():
                    passed_part = line.split("passed")[0].strip().split()[-1]
                    if passed_part.isdigit():
                        tests_passed = int(passed_part)
                if "failed" in line.lower():
                    failed_part = line.split("failed")[0].strip().split()[-1]
                    if failed_part.isdigit():
                        tests_failed = int(failed_part)
        if "duration" in line.lower():
            duration = line.split("in")[-1].strip()
    
    return {
        "success": return_code == 0,
        "return_code": return_code,
        "stdout": output,
        "stderr": error,
        "summary": {
            "tests_run": tests_run,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "duration": duration
        },
        "lines": lines[:50]  # 只返回前50行
    }


@router.get("/run-tool-tests")
async def run_tool_tests():
    """运行工具调用测试"""
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/unit/test_tool_calling.py", "-v", "--tb=short"],
        cwd="f:/project/meetingmind/backend",
        capture_output=True,
        text=True,
        timeout=60
    )
    
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr
    }


@router.get("/run-agent-tests")
async def run_agent_tests():
    """运行Agent行为测试"""
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/unit/test_agent_behavior.py", "-v", "--tb=short"],
        cwd="f:/project/meetingmind/backend",
        capture_output=True,
        text=True,
        timeout=60
    )
    
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr
    }
