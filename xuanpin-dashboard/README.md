# xuanpin-dashboard

xuanpin-ai 选品系统前端 Dashboard。

## 技术栈

- Vue 3 + TypeScript
- Vite
- Element Plus
- ECharts
- Axios
- Vue Router

## 启动

```bash
# 安装依赖
npm install

# 启动开发服务器（默认 http://localhost:5173）
npm run dev
```

## 后端

需要 FastAPI 后端运行在 `http://127.0.0.1:8000`。

```bash
cd ../xuanpin-ai
uv run uvicorn app.api.main:app
```

## 构建

```bash
npm run build
npm run preview
```
