# Database — 数据库设计说明与迁移策略

## 职责

- **Schema 设计**：领域表设计说明（源头：`docs/project_architecture.md` §3 数据库设计）。
- **迁移策略**：所有结构变更走 Alembic（位于 `backend/alembic`），禁止手工改库。
- 本目录存放设计文档与说明，不存放运行时代码。

## 迁移工作流

```bash
cd backend
alembic upgrade head                                # 应用迁移
alembic revision --autogenerate -m "<描述>"        # 基于 ORM 模型生成（M1 起）
```

## M0 状态

- 已建立迁移机制与基线（`0001_baseline`，无业务表）。
- M1 将按架构文档 §3.2 引入核心表：`products`、`suppliers`、`orders`、`purchase_orders`、`customers`、`ai_agent_runs`、`event_log` 等。