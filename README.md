# Nuotao Outdoor AI OS

AI 原生户外电商操作系统：以数据为底座，用 AI Agent（产品经理 / 营销经理 / 供应链经理 / 客户经理 / 商业分析）驱动跨境户外 DTC 业务。规划详见 `docs/`。

## 当前阶段

- **M0（进行中）**：工程基座 —— FastAPI 后端、PostgreSQL + Alembic、Redis、Docker Compose、测试框架。
- 规划文档：`docs/business_context.md`、`docs/business_decisions.md`、`docs/product_strategy.md`、`docs/operating_rules.md`、`docs/project_architecture.md`、`docs/development_roadmap.md`。

## 项目结构

```text
backend/        # FastAPI 后端服务（app/ + alembic/ + tests/）
frontend/       # 管理控制台前端（M1 起正式搭建，当前为占位）
database/       # 数据库设计说明与迁移策略
agents/         # AI Agent 规格与定义（M1 起填充）
rules/          # 运营规则参数配置（按 operating_rules.md 落地）
knowledge/      # 品牌/产品/FAQ 知识库（供 Agent 只读访问）
docs/           # 规划与开发文档
tests/          # 跨层测试策略与 E2E 占位
```

## 快速启动（Docker）

前置：Docker + Docker Compose。

```bash
cp .env.example .env        # 按需修改
docker compose up --build   # 启动 postgres + redis + backend
```

- API 文档：http://localhost:8000/docs
- 存活探针：`GET /api/v1/healthz`
- 就绪探针：`GET /api/v1/readyz`（检查 PostgreSQL 与 Redis）

## 本地开发（不使用 Docker）

详见 `docs/development.md`。要点：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows；macOS/Linux 用 source .venv/bin/activate
pip install -e ".[dev]"
# 需要本机 PostgreSQL/Redis（或 docker compose up postgres redis -d）
alembic upgrade head
uvicorn app.main:app --reload
```

## 测试与质量

```bash
cd backend
pytest          # 运行测试
ruff check .    # 代码检查
```

## 工程规范

项目规则、编码规范、AI Agent 开发原则与数据安全原则见根目录 `AGENTS.md`。