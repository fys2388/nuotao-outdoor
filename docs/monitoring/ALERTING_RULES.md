# Grafana Alerting Configuration for Nuotao AI OS

## 告警规则

### 1. 服务可用性告警

```yaml
- title: "Backend API 不可用"
  uid: "backend-api-down"
  condition: "C"
  data:
    - uid: "A"
      refID: "A"
      datasourceUid: "prometheus"
      model:
        expr: "up{job=\"nuotao-backend\"}"
        queryType: "range"
        range: true
        instant: false
        editorMode: "code"
    - uid: "B"
      refID: "B"
      datasourceUid: "prometheus"
      model:
        expr: "up{job=\"nuotao-backend\"}"
        queryType: "range"
        range: true
        instant: false
        editorMode: "code"
    - uid: "C"
      refID: "C"
      type: "threshold"
      queryType: "threshold"
      params:
        - - 1
        - "A"
  ruleGroups:
    - uid: "service-availability"
      title: "服务可用性"
      interval: 60
      orgId: 1
      folderUID: ""
      namespaceUID: ""
      deleteDelay: 0
      version: 1
      editable: true
      paused: false
```

### 2. 资源使用率告警

```yaml
- title: "CPU 使用率过高"
  uid: "cpu-high-usage"
  condition: "C"
  data:
    - uid: "A"
      refID: "A"
      datasourceUid: "prometheus"
      model:
        expr: "100 - (avg by (instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)"
        queryType: "range"
        range: true
        instant: false
        editorMode: "code"
    - uid: "B"
      refID: "B"
      datasourceUid: "prometheus"
      model:
        expr: "100 - (avg by (instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100)"
        queryType: "range"
        range: true
        instant: false
        editorMode: "code"
    - uid: "C"
      refID: "C"
      type: "threshold"
      queryType: "threshold"
      params:
        - - 80
        - "A"
```

### 3. 数据库连接告警

```yaml
- title: "数据库连接数过高"
  uid: "db-connections-high"
  condition: "C"
  data:
    - uid: "A"
      refID: "A"
      datasourceUid: "prometheus"
      model:
        expr: "pg_stat_activity_count"
        queryType: "range"
        range: true
        instant: false
        editorMode: "code"
    - uid: "B"
      refID: "B"
      datasourceUid: "prometheus"
      model:
        expr: "pg_stat_activity_count"
        queryType: "range"
        range: true
        instant: false
        editorMode: "code"
    - uid: "C"
      refID: "C"
      type: "threshold"
      queryType: "threshold"
      params:
        - - 100
        - "A"
```

### 4. Nginx 连接告警

```yaml
- title: "Nginx 连接数过高"
  uid: "nginx-connections-high"
  condition: "C"
  data:
    - uid: "A"
      refID: "A"
      datasourceUid: "prometheus"
      model:
        expr: "nginx_connections_active"
        queryType: "range"
        range: true
        instant: false
        editorMode: "code"
    - uid: "B"
      refID: "B"
      datasourceUid: "prometheus"
      model:
        expr: "nginx_connections_active"
        queryType: "range"
        range: true
        instant: false
        editorMode: "code"
    - uid: "C"
      refID: "C"
      type: "threshold"
      queryType: "threshold"
      params:
        - - 500
        - "A"
```

## 使用说明

1. 将以上告警规则添加到 Grafana Alerting
2. 配置通知渠道 (Slack、Email、Webhook)
3. 设置告警路由规则
4. 测试告警触发

## 参考文档

- [Grafana Alerting 文档](https://grafana.com/docs/grafana/latest/alerting/)
- [PromQL 参考](https://prometheus.io/docs/prometheus/latest/querying/basics/)