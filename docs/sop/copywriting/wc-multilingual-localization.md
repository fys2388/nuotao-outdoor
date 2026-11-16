# WC 多语言本地化 Prompt

> **对应 SOP**：`wc-ai-content-sop-v1.0.md` Phase ⑤
> **适用场景**：多语言站点、国际化市场
> **基础语言**：英文（US）

---

## 用途

将英文文案本地化为其他市场语言。注意：**不是简单翻译，是本地化**（语气、用词、文化适配）。

## 主要市场差异

| 语言 | 语气调整 | 关键词策略 |
|---|---|---|
| EN-US | 直白、量化、行动导向 | 使用 Helium10 Keyword Exporter |
| EN-UK | 英式拼写、克制、正式 | 独立关键词库 |
| DE | 简洁、精确、无感叹号 | 德语连字符长词需注意 |
| FR | 优雅、诗意、复合句 | 法语音节平衡 |
| ES | 热情、家庭感、社交属性 | 西语关键词密度高 |
| JP | 敬语、含蓄、场景描述 | 全角字符注意宽度 |
| AR | 从右至左排版、文化适配 | 阿拉伯语专有词库 |

---

## Prompt 模板

```markdown
# Role
You are a native-level [TARGET LANGUAGE] copywriter with 10+ years 
experience on DTC brands in [TARGET MARKET].

# Source Content (English)
- name: [EN_NAME]
- short_description: [EN_SHORT_DESC]
- description: [EN_DESCRIPTION]
- meta_title: [EN_META_TITLE]
- meta_description: [EN_META_DESCRIPTION]
- slug: [EN_SLUG]

# Product Context
- Product: [PRODUCT]
- Real product specs: [SPEC YAML]
- Brand voice: direct, data-backed, no hype
- Buyer persona (localized): [LOCALIZED_PERSONA]
- Cultural considerations: [CULTURAL_NOTES]

# Hard Constraints
- Target language: [TARGET LANGUAGE]
- Character limits preserved from source
- NO hype words (localized equivalents of Best/No.1/Free)
- NO direct machine translation artifacts
- NO Chinese characters
- Must respect local cultural sensitivities
- Must use local spelling (UK vs US English, etc.)
- Must use local currency and measurement system
- Must align with local advertising regulations

# Cultural Adaptation Rules
- [MARKET] market: [specific rules]
- Avoid: [taboo words/concepts]
- Use: [local idioms/phrases]

# Output Format (strict JSON)
{
  "target_language": "de",
  "name": "...",
  "short_description": "...",
  "description": "...",
  "meta_title": "...",
  "meta_description": "...",
  "slug": "kebab-case-with-keyword",
  "localization_notes": ["..."],
  "character_counts": {
    "name": 0,
    "short_description": 0,
    "meta_title": 0,
    "meta_description": 0
  }
}
```

---

## 示例（EN → DE）

**输入（EN）**：
- name: "Nuotao Portable Folding Camp Chair 45-Second Setup 600D Oxford 1.2kg Lightweight"
- short_description: "Premium 6mm TPE yoga mat with alignment lines - joint-friendly cushioning for daily practice."
- Price: $39.99

**输出（DE）**：
```json
{
  "target_language": "de",
  "name": "Nuotao Faltstuhl 45-Sekunden-Aufbau 600D Oxford 1,2 kg Ultraleicht",
  "short_description": "Hochwertige 6mm TPE Yogamatte mit Ausrichtungs Linien - gelenkschonende Polsterung für tägliche Praxis.",
  "localization_notes": [
    "Decimal separator changed from '.' to ','",
    "German compound words used",
    "No hype words, precise tone maintained"
  ],
  "character_counts": {
    "name": 78,
    "short_description": 118
  }
}
```

---

## 验收 Checklist

- [ ] 目标语言正确
- [ ] 字符限制保持
- [ ] 无机器翻译痕迹
- [ ] 本地化用词准确（非直译）
- [ ] 文化敏感性适配
- [ ] 拼写符合当地标准（UK vs US）
- [ ] 货币/单位系统本地化
- [ ] 无禁词（本地化版本）
- [ ] 无中文
- [ ] 符合当地广告法规

---

## 版本记录

- v1.0 (2026-09-27)：初版
