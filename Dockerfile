# 基于官方精简 Python 镜像构建
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装必要的系统工具与时区设置
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai
ENV PYTHONUNBUFFERED=1
ENV NO_PROXY=*

RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    gcc \
    curl \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖配置并预安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 暴露 Streamlit 默认服务端口
EXPOSE 8501

# 数据持久化目录声明
VOLUME ["/app/data"]

# 容器健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

# 启动服务
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
