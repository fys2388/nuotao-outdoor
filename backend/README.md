# Nuotao AI OS — Backend

FastAPI 后端服务（M0 工程基座）。业务 Agent 与领域模块将在 M1+ 按
`docs/project_architecture.md` 规划逐步加入。

## 结构

```text
backend/
  app/
    api/v1/endpoints/  # API 路由（只做参数校验与转发）
    core/              # config / logging / database / redis
    models/            # ORM 模型（M1 起填充）
    schemas/           # Pydantic 出入参（M1 起填充）
    services/          # 业务服务层（M1 起填充）
    integrations/      # 外部系统适配（M1 起填充）
    agents/            # AI Agent（M1 起填充，仅经 services/rules 访问数据）
    tasks/             # 后台任务（M1 起填充）
  alembic/             # 数据库迁移
  tests/               # pytest 测试
```

## 本地开发

见 `docs/development.md`。