import requests
import json
import pytest

API_BASE = "http://localhost:8000"


def _check_api_available():
    """检查 API 是否可用"""
    try:
        response = requests.get(f"{API_BASE}/api/v1/health", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _check_api_available(), reason="API server not running")
def test_graph_api_requests():
    """测试图谱 API 请求（需要 API 服务器运行）"""
    # 登录获取 token
    print("1. 登录获取 Token...")
    login_data = {"username": "testuser", "password": "test123"}
    response = requests.post(f"{API_BASE}/api/v1/users/login", json=login_data)
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {response.json()}")

    if response.status_code != 200:
        print("   登录失败，尝试注册...")
        register_data = {"email": "test2@test.com", "password": "test123", "username": "testuser2"}
        response = requests.post(f"{API_BASE}/api/v1/users/register", json=register_data)
        print(f"   注册状态码: {response.status_code}")
        print(f"   注册响应: {response.json()}")
        
        if response.status_code == 200:
            response = requests.post(f"{API_BASE}/api/v1/users/login", json=login_data)
            print(f"   再次登录状态码: {response.status_code}")

    if response.status_code == 200:
        token = response.json().get("data", {}).get("access_token")
        if token:
            print(f"   获取到 token: {token[:20]}...")
            headers = {"Authorization": f"Bearer {token}"}
            
            # 测试图谱 API
            print("\n2. 测试图谱 API...")
            
            # 尝试获取统计信息
            print("\n   测试 /graph/statistics")
            response = requests.get(f"{API_BASE}/api/v1/graph/statistics", headers=headers)
            print(f"   状态码: {response.status_code}")
            print(f"   响应: {response.text[:500]}")
            
            # 尝试构建并保存
            print("\n   测试 /graph/build-and-save")
            response = requests.post(f"{API_BASE}/api/v1/graph/build-and-save", headers=headers)
            print(f"   状态码: {response.status_code}")
            print(f"   响应: {response.text[:500]}")
    else:
        print(f"   登录失败: {response.text}")