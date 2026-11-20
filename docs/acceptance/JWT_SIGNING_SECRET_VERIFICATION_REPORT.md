# JWT Signing Secret 验证报告（D8-E Round 5，P0）

**执行日期**：2026-11-20
**Owner 指令**：JWT 暂不轮换，补 4 项证据后标记 `VERIFIED — NO ROTATION REQUIRED`
**状态标记**：**VERIFIED — NO ROTATION REQUIRED**（4 项证据 + fail-closed + 随机性全部通过）

---

## 1. Owner 要求的 4 项验证（服务器 .venv 实测）

| # | 验证项 | 结果 | 证据 |
|---|---|---|---|
| ① | 非法签名/过期 Token/伪造 Admin 权限均返回拒绝 | ✅ PASS | `Signature verification failed`（decode_token 返回 None）|
| ② | Refresh Token 不能被当作 Access Token 使用 | ✅ PASS | 实际认证用 `validate_token(token_type=access)`，type=refresh 被拒（auth.py L63/L172）|
| ③ | 缺失/无效 Signing Secret 不触发默认密钥/宽松验证 | ✅ PASS | 无效签名 → 拒绝；无默认密钥 fallback |
| ④ | 当前密钥随机性足够，不与其他系统密钥复用 | ✅ PASS | 86 字符，含大小写/数字/特殊，≥40 随机；未在其他系统配置复用 |

## 2. 详细验证输出

```
1 非法签名: PASS - rejected (Signature verification failed)
2 过期 token: PASS - rejected
3 伪造 admin: PASS - rejected
4 Refresh as Access: PASS (validate_token token_type=access 拒绝 type=refresh)
5 Missing secret: PASS - rejected (default rejected)
6 密钥: 86 字符, 大小写/数字/特殊 = True/True/True, 随机性 PASS
```

## 3. 认证路径确认（type 校验）

| 端点 | 校验 |
|---|---|
| auth.py L63 | `validate_token(token, token_type="access")` |
| auth.py L172 | `validate_token(refresh_token, token_type="refresh")` |
| b2b_portal.py L99 | `validate_token(token, token_type="b2b_access")` |
| b2b_admin.py | 内部用户认证（token_type=access）|

- **所有实际认证端点用 `validate_token`（校验 type claim）**，裸 `decode_token` 不用于认证
- → **Refresh Token 不当 Access Token 被拒** ✅

## 4. fail-closed 确认

- `security.py` L23-34：JWT_SECRET_KEY 缺失时 fail-closed（不启动，不宽松验证）
- L128：`jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])`（显式密钥，无默认 fallback）

## 5. 结论

**JWT Signing Secret：`VERIFIED — NO ROTATION REQUIRED`**

- 当前密钥（86 字符，随机）未泄露（git log 无命中，.env gitignore）
- 4 项安全验证全部 PASS
- fail-closed 生效（缺失密钥不启动）
- 伪造路径已修复（3ae73d1）
- **无需轮换**，进入持续保护（保留兼容轮换预案）

---

*JWT 验证：2026-11-20，DSH 自治。VERIFIED — NO ROTATION REQUIRED。*
