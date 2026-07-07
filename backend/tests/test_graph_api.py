"""测试知识图谱持久化 API"""
import httpx
import asyncio

API_BASE = "http://localhost:8000/api/v1"


async def test_graph_api():
    """测试知识图谱 API"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        
        # 1. 先登录获取 token
        print("1. 登录获取 Token...")
        login_response = await client.post(
            f"{API_BASE}/users/login",
            data={"username": "admin", "password": "admin123"}
        )
        
        if login_response.status_code != 200:
            print(f"   登录失败: {login_response.status_code}")
            print(f"   尝试注册用户...")
            
            # 尝试注册用户
            register_response = await client.post(
                f"{API_BASE}/users/register",
                json={
                    "email": "test@example.com",
                    "password": "testpass123",
                    "username": "testuser"
                }
            )
            
            if register_response.status_code == 200:
                print("   注册成功，尝试登录...")
                login_response = await client.post(
                    f"{API_BASE}/users/login",
                    data={"username": "testuser", "password": "testpass123"}
                )
            else:
                print(f"   注册也失败: {register_response.status_code}")
                return
        
        token_data = login_response.json()
        token = token_data.get("access_token")
        
        if not token:
            print(f"   获取 token 失败: {token_data}")
            return
        
        print(f"   ✅ 登录成功，获取到 token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. 获取图谱统计信息
        print("\n2. 获取图谱统计信息...")
        stats_response = await client.get(
            f"{API_BASE}/graph/statistics",
            headers=headers
        )
        
        print(f"   状态码: {stats_response.status_code}")
        if stats_response.status_code == 200:
            stats = stats_response.json()
            print(f"   内存图谱: {stats.get('memory', {})}")
            print(f"   Neo4j图谱: {stats.get('neo4j', {})}")
        else:
            print(f"   响应: {stats_response.text}")
        
        # 3. 构建并保存图谱
        print("\n3. 构建并保存图谱...")
        build_response = await client.post(
            f"{API_BASE}/graph/build-and-save",
            headers=headers
        )
        
        print(f"   状态码: {build_response.status_code}")
        if build_response.status_code == 200:
            result = build_response.json()
            print(f"   ✅ 构建并保存成功!")
            print(f"   消息: {result.get('message')}")
            print(f"   构建结果: {result.get('build')}")
            print(f"   保存结果: {result.get('save')}")
        else:
            print(f"   响应: {build_response.text}")
        
        # 4. 再次获取统计信息验证
        print("\n4. 再次获取统计信息验证...")
        stats_response = await client.get(
            f"{API_BASE}/graph/statistics",
            headers=headers
        )
        
        print(f"   状态码: {stats_response.status_code}")
        if stats_response.status_code == 200:
            stats = stats_response.json()
            print(f"   内存图谱: {stats.get('memory', {})}")
            print(f"   Neo4j图谱: {stats.get('neo4j', {})}")
            
            # 验证 Neo4j 中有数据
            neo4j_stats = stats.get('neo4j', {})
            if neo4j_stats.get('connected'):
                total_entities = neo4j_stats.get('total_entities', 0)
                total_relations = neo4j_stats.get('total_relations', 0)
                print(f"\n   🎉 Neo4j 验证成功!")
                print(f"   - 实体数量: {total_entities}")
                print(f"   - 关系数量: {total_relations}")
            else:
                print(f"   ⚠️ Neo4j 未连接")
        else:
            print(f"   响应: {stats_response.text}")


if __name__ == "__main__":
    print("=" * 60)
    print("  测试知识图谱持久化 API")
    print("=" * 60)
    asyncio.run(test_graph_api())
