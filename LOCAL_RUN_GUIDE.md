# XuanPin AI 本地运行指南（LOCAL_RUN_GUIDE）

把 XuanPin AI 当作日常工具使用：**双击一个脚本启动系统，双击另一个脚本执行每日采集**。

> 本指南对应 Phase 54 新增的两个启动脚本，不涉及任何业务代码或数据库改动。

---

## 一、第一次安装准备

只需在**第一次使用**时做一次。

### 1. 准备 Python 环境（二选一）

脚本会自动检测环境，**优先使用 conda 环境 `xuanpin-ai`，找不到时回退到项目自带的 `.venv`**。

- **方式 A：conda（若你习惯用 conda）**
  ```bat
  conda create -n xuanpin-ai python=3.11 -y
  conda activate xuanpin-ai
  pip install -e .
  ```

- **方式 B：项目自带 .venv（推荐，当前项目已就绪）**
  ```bat
  uv sync
  ```
  执行后会在项目根目录生成 `.venv\`，脚本会自动识别使用。

### 2. 准备前端依赖

```bat
cd xuanpin-dashboard
npm install
```
> 若忘记这一步也没关系：`start_xuanpin.bat` 检测到缺少 `node_modules` 时会自动执行 `npm install`。

### 3. 准备配置文件

确认项目根目录存在 `.env`（可从 `.env.example` 复制）：
```bat
copy .env.example .env
```

---

## 二、如何启动系统

**双击 `start_xuanpin.bat`** 即可，脚本会自动完成：

1. 进入项目目录并激活 Python 环境
2. 在独立窗口启动 **FastAPI 后端** → http://127.0.0.1:8000
3. 在独立窗口启动 **Vue Dashboard** → http://localhost:5173
4. 等待数秒后自动打开浏览器进入 Dashboard

后端与前端各自运行在**独立 cmd 窗口**，方便查看日志。

### 停止系统
直接**关闭对应的两个 cmd 窗口**即可停止后端和前端。

---

## 三、如何执行每日采集

**双击 `daily_run.bat`**，脚本会激活环境并执行：

```
python -m app.cli daily
```

该命令串联现有流程：**采集 → 入库评分 → 推荐池 → 供应链匹配 → 日报生成**。
执行完成后窗口会停留，可查看结果；执行失败会提示退出码并保留窗口。

> 每日任务无需先启动后端/前端，独立运行即可。执行结果可随后在 Dashboard 首页查看。

---

## 四、访问地址

| 服务 | 地址 |
|------|------|
| Dashboard 前端 | http://localhost:5173 |
| 后端 API | http://127.0.0.1:8000 |
| 健康检查 | http://127.0.0.1:8000/health |
| 首页概览接口 | http://127.0.0.1:8000/dashboard/home |

---

## 五、常见错误处理

| 现象 | 原因 | 解决 |
|------|------|------|
| 脚本报「未找到 conda 环境…也未找到 .venv」 | 环境未准备 | 按「第一次安装准备」创建 conda 环境或执行 `uv sync` |
| 后端窗口报「端口占用 / address already in use」 | 8000 端口被占用 | 关闭占用进程，或修改脚本中 `--port` 后重试 |
| 前端窗口报 `npm 不是内部或外部命令` | 未安装 Node.js | 安装 Node.js（含 npm）后重试 |
| 前端窗口报缺少依赖 / 模块找不到 | 依赖未安装 | 进入 `xuanpin-dashboard` 执行 `npm install` |
| 浏览器打开后页面显示「无法连接后端」 | 后端未就绪或启动失败 | 查看后端 cmd 窗口报错；确认 8000 端口正常 |
| Dashboard 数据为空 | 尚未采集数据 | 先双击 `daily_run.bat` 执行一次每日采集 |
| 每日任务采集为 0 条 | 目标平台风控 / 网络问题 | 属正常容错，查看 `logs\app.log`、`logs\crawler.log` |

---

## 六、说明

- 脚本仅做**启动封装**，未修改任何 Python / Vue 业务代码，未改动数据库。
- 后端启动模块为 `app.api.main:app`（项目实际入口）。
- 如需自定义端口 / 环境，直接编辑对应 `.bat` 文件中的命令行即可。
