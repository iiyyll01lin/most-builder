FROM python:3.10-slim

# 設定 Proxy
ENV http_proxy=http://10.6.254.210:3128
ENV https_proxy=http://10.6.254.210:3128
ENV no_proxy=localhost,127.0.0.1

WORKDIR /app

# 安裝 Nginx 和必要工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Python 依賴
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製後端程式碼
COPY backend/ ./backend/

# 複製前端檔案到 Nginx 目錄
COPY ddm_p1_full.html /var/www/html/index.html

# 複製 Nginx 配置
COPY nginx.conf /etc/nginx/sites-available/default

# 複製啟動腳本
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost/api/v1/health || exit 1

CMD ["/start.sh"]