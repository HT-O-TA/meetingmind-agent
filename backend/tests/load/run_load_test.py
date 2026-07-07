"""性能测试运行脚本"""
import subprocess
import os
import argparse
from datetime import datetime


def run_locust_test(scenario="normal_load", headless=True, output_dir="results"):
    """运行Locust性能测试"""
    scenarios = {
        "normal_load": {
            "users": 10,
            "spawn_rate": 1,
            "duration": "60s"
        },
        "medium_load": {
            "users": 50,
            "spawn_rate": 5,
            "duration": "120s"
        },
        "high_load": {
            "users": 100,
            "spawn_rate": 10,
            "duration": "180s"
        },
        "stress_test": {
            "users": 200,
            "spawn_rate": 20,
            "duration": "300s"
        }
    }
    
    if scenario not in scenarios:
        print(f"未知场景: {scenario}")
        print(f"可用场景: {list(scenarios.keys())}")
        return
    
    config = scenarios[scenario]
    
    # 获取当前脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(os.path.dirname(script_dir))
    
    # 创建输出目录（使用绝对路径）
    output_path = os.path.join(project_dir, output_dir)
    os.makedirs(output_path, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_file = os.path.join(output_path, f"locust_results_{scenario}_{timestamp}")  # 不带.csv，locust会自动添加
    html_file = os.path.join(output_path, f"locust_report_{scenario}_{timestamp}.html")
    
    print(f"🚀 开始性能测试: {scenario}")
    print(f"📊 配置: {config}")
    print(f"📁 输出目录: {output_path}")
    
    cmd = [
        "locust",
        "-f", os.path.join(project_dir, "tests", "load", "locustfile.py"),
        "--host=http://localhost:8000",
        "--users", str(config["users"]),
        "--spawn-rate", str(config["spawn_rate"]),
        "--run-time", config["duration"],
        "--csv", csv_file,
        "--html", html_file
    ]
    
    if headless:
        cmd.append("--headless")
    
    print(f"🔧 命令: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, cwd="backend", capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ 测试完成!")
            print(f"📈 报告文件: {html_file}")
            print(f"📉 数据文件: {csv_file}")
            
            # 打印关键指标摘要
            if os.path.exists(csv_file):
                print("\n📋 测试摘要:")
                with open(csv_file, 'r') as f:
                    lines = f.readlines()
                    if len(lines) > 1:
                        # 获取最后一行（汇总数据）
                        summary = lines[-1].strip().split(',')
                        print(f"  请求总数: {summary[0]}")
                        print(f"  失败数: {summary[1]}")
                        print(f"  平均响应时间: {summary[2]}ms")
                        print(f"  P50: {summary[3]}ms")
                        print(f"  P95: {summary[4]}ms")
                        print(f"  P99: {summary[5]}ms")
                        print(f"  QPS: {summary[6]}")
        else:
            print(f"❌ 测试失败")
            print(f"错误信息: {result.stderr}")
            
    except Exception as e:
        print(f"❌ 执行失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="运行Locust性能测试")
    parser.add_argument(
        "--scenario", "-s",
        choices=["normal_load", "medium_load", "high_load", "stress_test"],
        default="normal_load",
        help="测试场景"
    )
    parser.add_argument(
        "--headless", "-H",
        action="store_true",
        help="无头模式运行"
    )
    parser.add_argument(
        "--output", "-o",
        default="results",
        help="输出目录"
    )
    
    args = parser.parse_args()
    
    run_locust_test(
        scenario=args.scenario,
        headless=args.headless,
        output_dir=args.output
    )


if __name__ == "__main__":
    main()