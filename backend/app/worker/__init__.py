"""Agent worker package (M5.1).

Runs the generic Agent Execution Runtime as a modular-monolith worker:
consumes the Redis-Stream task queue, enforces policies (concurrency,
timeout, budget), drives retries and writes full audit. No concrete
business agent lives here - specific agent logic binds via the executor
extension point (M5.2+).
"""
