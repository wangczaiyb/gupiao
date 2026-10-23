"""
一键启动脚本 (Quick Launcher)
专为非专业程序员设计，只需在终端运行:
    python run.py
即可自动配置环境、检查端口并在默认浏览器中弹出中文波段交易辅助系统。
"""

import os
import subprocess
import sys
import webbrowser


def main():
    print("=" * 60)
    print("🚀 正在启动 A 股波段交易辅助系统...")
    print("=" * 60)

    # 检查核心依赖
    required_pkgs = ["streamlit", "plotly", "pandas", "numpy", "akshare"]
    missing = []
    for pkg in required_pkgs:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"⚠️ 正在自动安装缺失依赖: {', '.join(missing)} ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    # 确保本地缓存和数据目录存在
    os.makedirs("data/cache", exist_ok=True)
    os.makedirs("data/exports", exist_ok=True)

    app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
    port = os.environ.get("APP_PORT", "8501")

    print(f"✨ 系统已就绪，正在启动 Web 交互服务 (端口: {port}) ...")
    print("💡 浏览器将自动打开，若未弹出请手动访问: http://localhost:8501")
    print("=" * 60)

    # 启动 streamlit 进程
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        app_path,
        "--server.port",
        port,
        "--server.headless",
        "false",
        "--theme.base",
        "light",
    ]

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n🛑 服务已安全退出。")


if __name__ == "__main__":
    main()
