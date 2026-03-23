#!/bin/bash

# 啟動後端 (背景執行)
cd /app/backend
uvicorn main:app --host 127.0.0.1 --port 8000 &

# 等待後端啟動
sleep 3

# 啟動 Nginx (前景執行)
nginx -g "daemon off;"