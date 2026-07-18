# XuanPin AI

企业级 AI 驱动的应用程序。

## 项目结构

```
xuanpin-ai/
├── app/
│   ├── crawler/     # 爬虫模块
│   ├── config/      # 配置管理
│   ├── database/    # 数据库操作
│   ├── models/      # 数据模型
│   ├── services/    # 业务逻辑层
│   ├── utils/       # 工具函数
│   └── ai/          # AI / LLM 集成
├── logs/            # 日志文件
├── storage/         # 本地存储
├── tests/           # 测试
├── scripts/         # 脚本工具
├── .env.example     # 环境变量示例
├── pyproject.toml   # 项目配置与依赖
└── main.py          # 入口文件
```

## 环境要求

- Python >= 3.11
- [uv](https://github.com/astral-sh/uv) 包管理器

## 快速开始

### 1. 安装 uv（如未安装）

```bash
pip install uv
```

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入实际配置
```

### 4. 运行项目

```bash
uv run python main.py
```

## 开发

```bash
# 安装开发依赖
uv sync --dev

# 运行测试
uv run pytest

# 代码检查
uv run ruff check .

# 类型检查
uv run mypy .
```

## 许可证

MIT
