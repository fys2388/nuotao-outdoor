# Agent 自动分发系统配置
# 路径: backend/app/scheduler/agent_scheduler_config.py
# 作用: 统一管理 Agent 调度器的配置项

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentSchedulerConfig:
    """Agent 调度器配置。

    所有配置均可通过环境变量覆盖：
    - AGENT_SCHEDULER_ENABLED: 是否启用调度器
    - AGENT_EXECUTION_HOUR: 每日执行小时（UTC）
    - AGENT_EXECUTION_MINUTE: 每日执行分钟（UTC）
    - AGENT_COST_BUDGET_MONTHLY: 每月成本预算（美元）
    """

    # 调度器开关
    enabled: bool = True

    # 每日执行时间（UTC，对应北京时间 +8）
    # 默认 00:00 UTC = 08:00 北京时间
    execution_hour: int = 0
    execution_minute: int = 0

    # 调度器检查间隔（秒）
    tick_interval: int = 60

    # 成本护栏（美元）
    monthly_cost_budget: float = 100.0
    cost_alert_threshold: float = 0.8  # 达到预算80%时告警

    # 执行超时（秒）
    agent_execution_timeout: int = 300

    # 重试配置
    max_retries: int = 2
    retry_delay_seconds: int = 30

    # 启用的 Agent 列表（空列表表示全部启用）
    enabled_agents: list[str] = field(default_factory=list)

    # 禁用的 Agent 列表
    disabled_agents: list[str] = field(default_factory=list)

    # 日志配置
    log_level: str = "INFO"
    log_to_file: bool = True
    log_file_path: str = "logs/agent_scheduler.log"

    # 审批配置（与 AGENTS.md 保持一致）
    # 高风险操作必须进入审批队列，人工确认后执行
    require_human_approval: bool = True
    high_risk_actions: list[str] = field(default_factory=lambda: [
        "restock_inventory",
        "create_purchase_order",
        "optimize_campaign",
        "adjust_pricing",
        "process_return",
        "trigger_churn_prevention",
    ])

    # 降级配置
    # LLM 不可用时降级到规则引擎，规则引擎不可用时降级到人工
    enable_fallback: bool = True
    fallback_chain: list[str] = field(default_factory=lambda: [
        "llm",
        "rule_engine",
        "human",
    ])

    def get_enabled_agents(self) -> list[str]:
        """获取启用的 Agent 列表。

        Returns:
            启用的 Agent ID 列表
        """
        all_agents = [
            "product_analyst",
            "marketing_manager",
            "supply_chain_manager",
            "customer_manager",
            "business_analyst",
        ]

        if self.enabled_agents:
            return [a for a in all_agents if a in self.enabled_agents]

        if self.disabled_agents:
            return [a for a in all_agents if a not in self.disabled_agents]

        return all_agents

    def is_agent_enabled(self, agent_id: str) -> bool:
        """检查指定 Agent 是否启用。

        Args:
            agent_id: Agent ID

        Returns:
            是否启用
        """
        return agent_id in self.get_enabled_agents()

    def is_high_risk_action(self, action: str) -> bool:
        """检查操作是否为高风险操作。

        Args:
            action: 操作类型

        Returns:
            是否高风险
        """
        return action in self.high_risk_actions


# 全局配置实例
_config: AgentSchedulerConfig | None = None


def get_config() -> AgentSchedulerConfig:
    """获取全局配置实例。

    Returns:
        AgentSchedulerConfig 实例
    """
    global _config
    if _config is None:
        _config = AgentSchedulerConfig()
    return _config


def reload_config() -> AgentSchedulerConfig:
    """重新加载配置。

    Returns:
        新的 AgentSchedulerConfig 实例
    """
    global _config
    _config = AgentSchedulerConfig()
    return _config
