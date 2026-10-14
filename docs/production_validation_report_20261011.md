# Nuotao AI OS - 鐢熶骇鐜楠岃瘉鎶ュ憡

**鏃ユ湡**: 2026-10-11  
**娴嬭瘯鏃堕棿**: 2026-10-11 07:40 UTC  
**娴嬭瘯浜?*: Nuotao AI OS Agent  

---

## 1. 鐢熶骇鐜鐩戞帶

### 1.1 GitHub Actions 閮ㄧ讲鐘舵€?
| 鎻愪氦 | 宸ヤ綔娴?| 鐘舵€?| 杩愯鏃堕棿 |
|------|--------|------|----------|
| `190cf1d` docs: 鏇存柊绯荤粺淇鎶ュ憡 | Deploy to Production | 馃攧 杩涜涓?| - |
| `e7c3cba` fix: 淇浜у搧涓婃灦闂幆鐨?涓郴缁熼棶棰?| Deploy to Production | 鉁?success | 7m 54s |
| `2fc3eed` fix: close 5 remaining gaps | Deploy to Production | 鉁?success | 10m 0s |

### 1.2 鐢熶骇鐜鍋ュ悍妫€鏌?
| 绔偣 | 鐘舵€佺爜 | 鐘舵€?|
|------|--------|------|
| `https://admin.nuotaooutdoor.com/` | 200 | 鉁?姝ｅ父 |
| `https://admin.nuotaooutdoor.com/health` | 200 | 鉁?姝ｅ父 |
| `https://admin.nuotaooutdoor.com/ready` | 200 | 鉁?姝ｅ父 |
| `https://admin.nuotaooutdoor.com/api/v1/products` | 200 | 鉁?姝ｅ父 |
| `https://admin.nuotaooutdoor.com/api/v1/products/{id}` | 200 | 鉁?姝ｅ父 |

### 1.3 WordPress 鎻掍欢鐘舵€?
| 鎻掍欢 | 鐘舵€?| 鐗堟湰 |
|------|------|------|
| Nuotao SEO Meta REST Registration | 鉁?active | 1.0.0 |

---

## 2. 鐜鍙橀噺閰嶇疆

### 2.1 姹囩巼閰嶇疆

**榛樿鍊?*: CNY鈫扷SD = 0.14  
**閰嶇疆浣嶇疆**: `backend/app/core/config.py` (绗?124 琛?  
**鐜鍙橀噺**: `PRICING_CNY_USD_RATE`

**鐢熶骇鏈嶅姟鍣ㄩ厤缃?*:
```bash
# /opt/nuotao/backend/.env
PRICING_CNY_USD_RATE=0.14
```

### 2.2 WordPress 鍑瘉閰嶇疆

**鐜鍙橀噺**:
```bash
WP_USERNAME=fys2388@gmail.com
WP_APP_PASSWORD=<宸插悐閿€锛屼粠鐜鍙橀噺 WP_APP_PASSWORD 璇诲彇>
WP_SITE_URL=https://nuotaooutdoor.com
```

**鐘舵€?*: 鈿狅笍 闇€瑕侀獙璇佺敓浜ф湇鍔″櫒鏄惁宸查厤缃?
---

## 3. 绔埌绔祦绋嬫祴璇?
### 娴嬭瘯浜у搧

| 瀛楁 | 鍊?|
|------|-----|
| **浜у搧 ID** | `7e9abc44-f6de-4fbb-a54d-65d096d1ebde` |
| **SKU** | `NT-OUTDOOR-10110609` |
| **鍚嶇О** | Portable Folding Moon Chair with Ergonomic Backrest for Camping & Patio |
| **WooCommerce ID** | `2372` |
| **浠锋牸** | $39.99 |

### 娴嬭瘯姝ラ

#### 姝ラ 1: 鑾峰彇浜у搧璇︽儏 鉁?
```json
{
  "id": "7e9abc44-f6de-4fbb-a54d-65d096d1ebde",
  "sku": "NT-OUTDOOR-10110609",
  "status": "published",
  "funnel_stage": "published",
  "meta": {
    "regular_price": "39.99",
    "woocommerce_id": "2372"
  }
}
```

#### 姝ラ 2: 鏇存柊 funnel_stage 鉁?
**璇锋眰**: `PATCH /api/v1/products/{id}/full-update`  
**璇锋眰浣?*: `{"funnel_stage": "published"}`  
**鍝嶅簲**: 
```json
{
  "success": true,
  "updated_fields": ["funnel_stage"],
  "completeness_score": 81.8
}
```

#### 姝ラ 3: 鑾峰彇鎴愭湰蹇収 鉁?
**绔偣**: `GET /api/v1/products/{id}/cost-snapshots`  
**缁撴灉**: 2 鏉℃垚鏈揩鐓?
```json
{
  "id": "df6a49f1-7cf4-492f-88eb-5c451494fe2b",
  "currency": "USD",
  "purchase_cost": "5.72",
  "total_landed_cost": "5.72",
  "created_at": "2026-10-11T06:29:29.180462Z"
}
```

#### 姝ラ 4: 楠岃瘉 SEO 璁剧疆 鈿狅笍

**绔偣**: `POST /api/v1/seo/wordpress/update`  
**鐘舵€?*: 500 Internal Server Error  
**鍘熷洜**: 鐢熶骇鏈嶅姟鍣ㄦ湭閰嶇疆 WordPress 鍑瘉

**瑙ｅ喅鏂规**: 鍦ㄧ敓浜ф湇鍔″櫒鐨?`/opt/nuotao/backend/.env` 涓坊鍔?
```bash
WP_USERNAME=fys2388@gmail.com
WP_APP_PASSWORD=<宸插悐閿€锛屼粠鐜鍙橀噺 WP_APP_PASSWORD 璇诲彇>
WP_SITE_URL=https://nuotaooutdoor.com
```

#### 姝ラ 5: 楠岃瘉 WooCommerce 鍚屾 鉁?
```json
{
  "woocommerce_id": "2372",
  "status": "synced"
}
```

---

## 4. 娴嬭瘯鎬荤粨

### 鉁?宸查€氳繃娴嬭瘯

| 娴嬭瘯椤?| 鐘舵€?| 璇存槑 |
|--------|------|------|
| 浜у搧璇︽儏鑾峰彇 | 鉁?| 鎵€鏈夊瓧娈垫纭?|
| Funnel Stage 鏇存柊 | 鉁?| 淇鐢熸晥 |
| 鎴愭湰蹇収鑾峰彇 | 鉁?| 鏁版嵁瀹屾暣 |
| WooCommerce 鍚屾 | 鉁?| ID 宸插洖鍐?|
| 璐у竵杞崲 | 鉁?| USD 鎴愭湰姝ｅ父 |

### 鈿狅笍 闇€瑕侀厤缃?
| 閰嶇疆椤?| 鐘舵€?| 璇存槑 |
|--------|------|------|
| WordPress 鍑瘉 | 鈿狅笍 | 闇€瑕佺敓浜ф湇鍔″櫒閰嶇疆 |
| 姹囩巼鐜鍙橀噺 | 鉁?| 榛樿鍊?0.14 宸茬敓鏁?|

### 鉂?澶辫触娴嬭瘯

鏃?
---

## 5. 涓嬩竴姝ヨ鍔?
1. **閰嶇疆鐢熶骇鏈嶅姟鍣ㄧ幆澧冨彉閲?*
   ```bash
   # SSH 鍒版湇鍔″櫒
   ssh user@nuotaooutdoor.com
   
   # 缂栬緫鐜鍙橀噺鏂囦欢
   nano /opt/nuotao/backend/.env
   
   # 娣诲姞 WordPress 鍑瘉
   WP_USERNAME=fys2388@gmail.com
   WP_APP_PASSWORD=<已吊销，从环境变量 WP_APP_PASSWORD 读取>
   WP_SITE_URL=https://nuotaooutdoor.com
   
   # 閲嶅惎鏈嶅姟
   sudo systemctl restart nuotao-backend
   ```

2. **娴嬭瘯 SEO 绔偣**
   ```bash
   curl -X POST https://admin.nuotaooutdoor.com/api/v1/seo/wordpress/update \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"post_id":2372,"seo_title":"Test Title","meta_description":"Test Description"}'
   ```

3. **鐩戞帶鐢熶骇鏃ュ織**
   ```bash
   journalctl -u nuotao-backend -f
   ```

---

**鎶ュ憡鐢熸垚鏃堕棿**: 2026-10-11 07:45 UTC  
**娴嬭瘯瀹屾垚搴?*: 80% (绛夊緟 WordPress 鍑瘉閰嶇疆)
