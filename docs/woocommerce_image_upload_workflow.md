# WooCommerce 浜у搧鍥剧墖鑷姩鍖栧悓姝?
## 鐘舵€侊細宸茶窇閫氬苟淇涓€娆¤法浜у搧鍥剧墖姹℃煋浜嬫晠锛?026-10-18锛?
浜у搧 2565锛堟墜鐢电瓛锛? 寮犺嫳鏂囩數鍟嗗浘宸蹭笂绾夸笖 alt 姝ｇ‘锛?浜у搧 2549锛堥槻姘磋锛夊師鏈?5 寮犲浘鏈鐮村潖锛?鍘嗗彶閬楃暀鐨勯噸澶嶉檮浠跺凡娓呯悊銆?
---

## 涓€銆佸繀椤讳娇鐢ㄤ袱濂楄璇?
| 鐩爣 | 绔偣 | 璁よ瘉鏂瑰紡 |
|---|---|---|
| 涓婁紶鍥剧墖鍒板獟浣撳簱 | `/wp-json/wp/v2/media` | **WordPress Application Password**锛堢敤鎴?`AI1`锛?|
| 璁剧疆浜у搧鍥剧墖 | `/wp-json/wc/v3/products/{id}` | **WooCommerce consumer key/secret锛坮ead_write锛?* |

澶辫触杩囩殑鍋氭硶锛堥伩鍏嶉噸韪╋級锛?
1. **WC consumer key 璋?WP 濯掍綋绔偣** 鈫?`invalid_username` 401銆?   WP 濯掍綋绔偣鍙 WordPress 鐢ㄦ埛韬唤銆?2. **WC 浜у搧 API 浼?base64 `images[].src`** 鈫?`woocommerce_product_image_upload_error`銆?   `src` 鍙帴鍙楀彲鎶撳彇鐨勮繙绋?URL锛屼笉鏀寔 base64 data URI銆?3. **绠＄悊鍛樼櫥褰曞瘑鐮佸仛 Basic Auth** 鈫?`Unknown username` / `incorrect_password`銆?   REST 闇€瑕?Application Password锛屼笉鏄櫥褰曞瘑鐮併€?4. **Application Passwords 闈㈡澘娑堝け** 鈫?`is_ssl()` 鍦ㄥ弽鍚戜唬鐞嗕笅杩斿洖 false锛?   WordPress 鍒ゅ畾銆岄潪 HTTPS 涓嶆敮鎸佸簲鐢ㄥ瘑鐮併€嶃€?
### 涓€娆℃€т慨澶嶏細鍚敤 Application Passwords

Code Snippets 涓凡鍒涘缓骞舵縺娲?snippet `Enable Application Passwords for REST API`锛?
```php
add_filter( 'wp_is_application_passwords_available', '__return_true' );
add_filter( 'wp_is_application_passwords_supported', '__return_true' );
```

> 搴旂敤瀵嗙爜**鍙湪鍒涘缓鏃舵樉绀轰竴娆?*锛屽繀椤诲綋鍦轰繚瀛樸€?> 褰㈠ `yhY8 qYGK o6tD sg1T IRoe peaO`锛? 缁?4 瀛楃锛屾敞鎰忓尯鍒嗗瓧姣?O 鍜屾暟瀛?0锛夈€?
---

## 浜屻€佷袱涓嚧鍛介櫡闃憋紙鏈浜嬫晠鏍瑰洜锛?
### 闄烽槺 1锛氭寜鏂囦欢鍚嶆煡閲嶅鑷磋法浜у搧鍊熺敤鍥剧墖

涓嶅悓 SKU 閮戒娇鐢ㄤ簡 `01_main_image_white_background.png` 杩欑被閫氱敤鏂囦欢鍚嶃€?鏃╂湡鑴氭湰浠呮寜鏂囦欢鍚嶅尮閰嶅獟浣撳簱锛屾妸**闃叉按琚嬩骇鍝侊紙2549锛夌殑涓诲浘**
褰撴垚鏈骇鍝併€屽凡瀛樺湪鐨勫浘銆嶅鐢ㄤ簡銆?
鍚庢灉锛氭墜鐢电瓛浜у搧鏄剧ず闃叉按琚嬬缉鐣ュ浘锛涘悓鏃惰闄勪欢鐨勪腑闂村昂瀵哥缉鐣ュ浘
锛坄-600x600.png` 绛夛級浠嶅睘浜庨槻姘磋鍘熷浘锛屽嵆浣垮師鍥捐瑕嗙洊涔熶細鏄剧ず閿欏浘銆?
**淇鍘熷垯**锛氬彧澶嶇敤銆?*褰撳墠宸茶鏈骇鍝?images 寮曠敤**銆嶇殑闄勪欢
锛堣 `find_media_id(filename, owned_ids)`锛夛紝浠庢牴涓婃潨缁濆€熺敤銆?
### 闄烽槺 2锛歀iteSpeed/CDN 缂撳瓨 REST API 鍝嶅簲

琛ㄧ幇涓恒€孭UT 杩斿洖 200 涓斿搷搴斾綋鏄柊鐨勶紝绱ф帴鐫€ GET 鍙堟槸鏃у€笺€嶃€?杩欎笉鏄啓鍏ュけ璐ワ紝鑰屾槸 HTTP 灞傜紦瀛樹簡 `GET /wp-json/wc/v3/products/{id}`銆?
鍚庢灉锛氳剼鏈鍒ゅ啓鍏ュけ璐?鈫?閲嶅涓婁紶 鈫?濯掍綋搴撳爢绉濂楅噸澶嶉檮浠躲€?
**淇鍘熷垯**锛氭墍鏈?REST 璇诲啓璇锋眰閮借拷鍔犳椂闂存埑 `?cb=<epoch_ms>`锛?骞惰缃?`Cache-Control: no-cache, no-store`銆?`verify_product_images()` 閲屽悓鏃跺仛浜嗛噸璇曢€€閬裤€?
> 鑻ユ€€鐤戜粛鏈夋畫鐣欑紦瀛橈紝鍙湪
> `WooCommerce 鈫?Status 鈫?Tools 鈫?Clear transients` 鎵嬪姩娓呯悊銆?
---

## 涓夈€佸嚟璇侊紙宸插啓鍏?`backend/.env.production`锛?
```
WOOCOMMERCE_BASE_URL=https://nuotaooutdoor.com
WOOCOMMERCE_CONSUMER_KEY=<1688_APP_KEY>
WOOCOMMERCE_CONSUMER_SECRET=<1688_APP_SECRET>

WP_USERNAME=AI1
WP_APPLICATION_PASSWORD=yhY8 qYGK o6tD sg1T IRoe peaO
WP_MEDIA_UPLOAD_ENABLED=true
```

鏃у彧璇诲瘑閽ュ浠斤細`backend/.env.env.production.bak`

---

## 鍥涖€佷娇鐢ㄦ柟寮?
```bash
# 涓婁紶骞舵妸鍥剧墖鎸傚埌浜у搧锛堝箓绛夛細宸茶鏈骇鍝佸紩鐢ㄧ殑鍥句笉浼氶噸澶嶄笂浼狅級
python backend/tools/wc_image_workflow.py \
    --product-id 2565 \
    --images-dir "C:/path/to/images" \
    --order "ys7007_01_main_image.png,ys7007_02_hero_benefits.png,..." \
    --alts "alt1||alt2||alt3"

# 鍚屾椂娓呯悊琚浛鎹笅鏉ョ殑鏃ч檮浠?python backend/tools/wc_image_workflow.py ... --cleanup-old
```

鑴氭湰娴佺▼锛?
1. 璇讳骇鍝佸綋鍓?images 鈫?寰楀埌 `owned_ids`锛?2. 閫愪釜鐩爣鏂囦欢鍚嶅湪濯掍綋搴撴煡鎵撅紝**鍙湁鍛戒腑 owned_ids 鎵嶅鐢?*锛?3. 鏈懡涓垯涓婁紶锛堝彲閫?`--alts` 鍐欏叆 alt 鏂囨湰锛夛紱
4. 鎸?`--order` 椤哄簭缁勮 `images[]`锛屼竴娆?PUT 瑕嗙洊浜у搧鍥鹃泦锛?5. `verify_product_images()` 甯?cache-buster 閲嶈瘯鏍￠獙锛?6. `--cleanup-old` 鏃跺垹闄ゃ€屽師鏉ュ湪浜у搧涓娿€佷絾涓嶅湪鏂伴『搴忛噷銆嶇殑闄勪欢銆?
---

## 浜斻€佸綋鍓嶄骇鍝佸浘鐗?
### 鎵嬬數绛?2565

| 椤哄簭 | 濯掍綋 ID | 鏂囦欢鍚?|
|---|---|---|
| 1锛堜富鍥撅級 | 2575 | ys7007_01_main_image.png |
| 2 | 2576 | ys7007_02_hero_benefits.png |
| 3 | 2577 | ys7007_03_key_features.png |
| 4 | 2578 | ys7007_04_size_and_colors.png |
| 5 | 2579 | ys7007_05_outdoor_lifestyle.png |
| 6 | 2580 | ys7007_06_six_lighting_modes.png |

alt 宸插叏閮ㄥ啓鍏ワ紙渚嬪涓诲浘
`nuotao mini rechargeable flashlight - main product photo on white background`锛夈€?
### 闃叉按琚?2549锛堟湭鍙楀奖鍝嶏級

`2555 01_main_image_white_background.png` + `2556~2559`锛屽叡 5 寮狅紝alt 淇濇寔鍘熸牱銆?
---

## 鍏€佹枃妗堜慨姝ｈ褰曪紙2026-10-18锛屽凡瀹屾垚锛?
### 闂锛氭枃妗堟槸閿欑殑锛屼笌绱犳潗涓嶆槸鍚屼竴娆惧晢鍝?
浜у搧 2565 涓婄嚎鏃剁敤鐨勬枃妗堝鐢ㄤ簡銆岄€氱敤杩蜂綘鎵嬬數銆嶆ā鏉匡紝涓庢寜渚涘簲鍟嗕俊鎭埗浣滅殑鍥剧墖
瀹屽叏瀵逛笉涓婏細

| 鍙傛暟 | 鍥剧墖/渚涘簲鍟嗕俊鎭?| 鍘熸枃妗?| 鍒ゅ畾 |
|---|---|---|---|
| 褰㈡€?| 鐭╁舰鍙屽厜婧愭劅搴斿伐浣滅伅 + 纾佸惛鑳屽す | 鍦嗘煴鎵嬬數 + 閲戝睘灏剧幆 | 閿?|
| 灏哄 | 58 mm 楂?| 9.5 cm | 閿?|
| 閲嶉噺 | 绾?31 g | 65 g | 閿?|
| 鏉愯川 | 宸ョ▼濉戞枡 | 鑸┖绾ч摑鍚堥噾銆侀槼鏋佹哀鍖?| 閿?|
| 鐏厜妯″紡 | 6 绉嶏紙鍚?red light / red strobe锛?| 3 绉嶏紙high/low/strobe锛?| 閿?|
| 鍏夋簮 | COB 娉涘厜 + 2 棰楄仛鍏夌伅鐝?| 鍗曚竴涓荤伅 | 閿?|
| 鎵嬪娍鎰熷簲 | 鏈夛紙SENSOR MODE锛?| 鏈彁鍙?| 婕?|
| 300 lm / 800 mAh / 8 h | 绱犳潗鏈爣娉?| 鍐欐 | 鏃犱緷鎹?|
| IPX4 | 鏈?| 鏈?| 瀵?|

闄勫甫闂锛氫骇鍝佽鍒嗗埌浜嗛敊璇垱寤虹殑绌哄垎绫?`ID 405 / 鍚嶇О "22"`锛?URL slug 杩樺甫鐫€ `300-lumens-8-hour-runtime`銆?
### 淇鍔ㄤ綔

1. **鏍囬**锛歚nuotao Mini Rechargeable Clip-On Work Light 鈥?6 Lighting Modes, Gesture Sensor, Magnetic Clip, IPX4 Waterproof`
2. **鐭?闀挎弿杩?*锛氭寜 6 妯″紡銆佸弻鍏夋簮銆佹墜鍔挎劅搴斻€佺鍚歌儗澶广€?00 mAh / 5 h 閲嶅啓
3. **灞炴€?*锛歚Style: Olive Green, Black`
4. **鏍囩**锛氭崲鎴?clip-on work light / COB floodlight / gesture sensor light / magnetic work light / red warning light / 6 lighting modes / IPX4 waterproof / rechargeable work light / camping light / hiking gear
5. **灏哄閲嶉噺瀛楁**锛歚3.0 脳 2.7 脳 5.8 cm`銆乣0.031 kg`锛堜箣鍓嶄负绌猴級
6. **鍒嗙被**锛氭敼涓?`Lighting & Power (ID 22)`锛屽垹闄ょ┖鍒嗙被 405锛?22"锛?7. **slug**锛歚nuotao-mini-rechargeable-clip-on-work-light`锛屾棫 URL 鑷姩 301

### 宸茬‘璁ょ殑鐢垫睜鍙傛暟锛堢敤鎴?2026-10-18 纭锛?
- 鐢垫睜瀹归噺锛?*400 mAh**锛堥噰鐢?1688 鍘熷鍊硷紝闈?800 mAh锛?- 浣庝寒缁埅锛?*5 灏忔椂**锛堥潪 8 灏忔椂锛?
### 浠嶉渶渚涘簲鍟嗚ˉ鍏呯殑鍙傛暟

- 瀹為檯娴佹槑鍊硷紙鍘熸枃妗堝啓 300 lm锛岀礌鏉愭棤鏍囨敞锛屽凡浠庢枃妗堜腑绉婚櫎锛?- 涓荤伅/鑱氬厜鐨勯瀹氳緭鍑轰笌灏勭▼

### 鏂囨淇鐨勬暀璁?
鏂囨鐢熸垚蹇呴』浠?*渚涘簲鍟嗗疄闄呰祫鏂欐垨宸茬‘璁ょ殑鍥剧墖淇℃伅**涓哄噯锛?绂佹濂楃敤鍚岀被浜у搧鐨勯€氱敤鍙傛暟銆備笂绾垮墠搴斿仛銆屾枃妗?鈫?鍥剧墖鍙傛暟涓€鑷存€с€嶆牎楠岋紝
鑷冲皯鏍稿锛氬舰鎬併€佸昂瀵搞€侀噸閲忋€佹潗璐ㄣ€佹ā寮忔暟閲忋€佺壒娈婂姛鑳斤紙鎰熷簲/纾佸惛/绾㈠厜锛夈€?
