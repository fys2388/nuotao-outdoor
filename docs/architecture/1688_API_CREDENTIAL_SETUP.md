# 1688 开放平台 API 凭证获取指南（simple.get 路线）

> 目标：摆脱会过期的浏览器 Cookie，改用长期有效的 API 密钥跑通真实商品数据。
> 你的账号 **已订购** `alibaba.product.simple.get`（能力名「获取已购买商家商品信息」，200 万次额度），
> **只需补两个凭证**即可跑通，无需申请、无 GMV 门槛、API 免费。
> 本文档不含任何密钥明文。密钥只进 GitHub Secret / 服务器 .env。

---

## 你需要提供 2 个值

| 凭证 | 环境变量 | 哪里拿 | 是否已有 |
|---|---|---|---|
| AppSecret | `ALI1688_APP_SECRET` | 开放平台控制台 → 你的应用 | ❌ 缺（导致长期跑 Mock） |
| AccessToken | `ALI1688_ACCESS_TOKEN` | 应用控制台 → 1688 授权 | ❌ 缺（simple.get 授权必需） |

AppKey 你已有：`ALI1688_APP_KEY = 2819733`。

---

## 步骤 1：拿 AppSecret

1. 打开 **https://open.1688.com/** ，用 1688 账号 `tb638676` 登录。
2. 进入 **控制台** → **应用管理**（或「我的应用」）。
3. 找到你的自用型应用（AppKey `2819733`）。
4. 点开应用详情，找到 **App Secret**（可能显示为「查看密钥」/「重置」）。
5. **复制 App Secret 值**（一长串字符）。

> 若控制台要求验证身份（短信/扫码），按提示完成。
> 若找不到应用，可能需要先「创建应用」——选「自用型应用」，填名称即可，AppKey 会自动生成（若与 2819733 不同，以实际为准并告知 DSH）。

## 步骤 2：拿 AccessToken（OAuth 授权）

`simple.get` 是需授权接口，必须带 AccessToken。获取方式：

1. 仍在 **https://open.1688.com/** 控制台，进入你的应用。
2. 找到 **「1688 授权」/「授权管理」/「获取 Token」** 入口。
3. 点击授权，用 `tb638676` 完成授权（可能跳转 1688 登录确认页）。
4. 授权成功后，控制台会显示 **AccessToken**（也可能叫 access_token）。
5. **复制 AccessToken 值**。

> AccessToken 有有效期，过期需重新授权/刷新。比浏览器 Cookie 稳定得多（通常数周~数月，且可程序化刷新）。

---

## 步骤 3：把两个值交给 DSH 接入（选一种）

### 方式 A（推荐，全自动）：粘进 GitHub Secret
1. 打开 `github.com/fys2388/nuotao-outdoor/settings/secrets/actions`
2. 新建/更新两个 Secret：
   - `ALI1688_APP_SECRET` → 粘 AppSecret
   - `ALI1688_ACCESS_TOKEN` → 粘 AccessToken
3. 回 DSH 一句「**Secret 粘好了**」，DSH 会：
   - 建/触发一个 workflow：从 Secret 读值 → 原子写入服务器 `.env` → 跑 `hotfix_oapi_diag.py` 验证 `simple.get` 返回真实数据
   - Cookie 全程掩码，不经聊天明文

### 方式 B：直接告诉 DSH 已在服务器 .env 手动填好
若你选择自己 SSH 填 `/opt/nuotao-ai-os/backend/.env` 的 `ALI1688_APP_SECRET=` 和 `ALI1688_ACCESS_TOKEN=`，
填完回 DSH 一句「**.env 填好了**」，DSH 触发诊断验证。

---

## 验证标准（DSH 接入后会自动检查）

跑 `scripts/hotfix_oapi_diag.py`，要求：
- `OAPI is_configured: True`
- `OAPI success: True`
- `OAPI source: 1688_open_api`（**非 mock**）
- `OAPI api_method: alibaba.product.simple.get`
- `OAPI subject:` 真实商品标题（非 "1688 Product" 占位）
- `OAPI price / sku_count / attr_count / images` 均为真实值

只要 subject 是真实商品名，即证明 **API 长期方案跑通**，从此不再依赖浏览器 Cookie。

---

## 常见问题

- **AppSecret 找不到/被隐藏**：点「重置密钥」会生成新的（旧的可能失效，属正常）。
- **AccessToken 过期**：重新走步骤 2 授权即可；后续可让 DSH 建自动刷新机制。
- **simple.get 报 `gw.APIUnsupported`**：说明路径 namespace 拆错——代码已显式登记正确元数据，若仍报错告知 DSH 排查。
- **报 `gw.APIACLDecline`**：那是 `product.get`（未订购）的错误，代码会自动降级到 `simple.get`；只要 simple.get 通即可。
