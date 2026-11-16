# 绗?姝ユ墽琛屾姤鍛婏細ChatGPT鍑哄浘 鈫?涓嬭浇 鈫?鏇存柊WC浜у搧鍥剧墖

## 浠诲姟姒傝堪
浠嶤hatGPT涓嬭浇7寮犺嫳鏂囩數鍟嗗浘鐗囷紝骞舵浛鎹ooCommerce浜у搧2593鐨勬墍鏈夊浘鐗囥€?
---

## 鎵ц姝ラ

### 姝ラ1锛氫粠ChatGPT涓嬭浇鍥剧墖ZIP鍖?
1. **瀹氫綅ChatGPT瀵硅瘽椤甸潰**
   - URL锛歨ttps://chatgpt.com/c/6ad04b48-17a8-83e9-a96b-0d14d8777c78
   - 鍦ㄥ璇濅腑鎵惧埌7寮犵敓鎴愮殑鍥剧墖
   - 鎵惧埌"Open 涓嬭浇 7 寮犺嫳鏂囩數鍟嗗浘 ZIP 鍘嬬缉鍖?閾炬帴锛園e162锛?
2. **鐐瑰嚮涓嬭浇ZIP鍖?*
   - 鐐瑰嚮ZIP涓嬭浇閾炬帴瑙﹀彂娴忚鍣ㄤ笅杞?   - 涓嬭浇璺緞锛歚C:\Users\绁為瓊涔嬩汉\Downloads\Nuotao_Backpack_Ecommerce_EN.zip`

3. **澶嶅埗ZIP鍒板伐浣滃尯骞惰В鍘?*
   ```powershell
   # 澶嶅埗鍒板伐浣滃尯
   Copy-Item "C:\Users\绁為瓊涔嬩汉\Downloads\Nuotao_Backpack_Ecommerce_EN.zip" `
     -Destination "E:\AI\nuotao-ai-os\Nuotao_Backpack_Ecommerce_EN.zip" -Force
   
   # 瑙ｅ帇
   Expand-Archive -Path "E:\AI\nuotao-ai-os\Nuotao_Backpack_Ecommerce_EN.zip" `
     -DestinationPath "E:\AI\nuotao-ai-os\backpack-images" -Force
   ```

4. **纭瑙ｅ帇鍚庣殑鏂囦欢**
   ```
   backpack-images\Nuotao_Backpack_Ecommerce_EN\
   鈹溾攢鈹€ 01-main-image-black.png       (1254脳1254, 1.79 MB)
   鈹溾攢鈹€ 02-color-options.png          (1536脳1024, 2.22 MB)
   鈹溾攢鈹€ 03-front-details.png          (1254脳1254, 2.31 MB)
   鈹溾攢鈹€ 04-back-panel-comfort.png     (1254脳1254, 2.20 MB)
   鈹溾攢鈹€ 05-outdoor-lifestyle.png      (1254脳1254, 2.33 MB)
   鈹溾攢鈹€ 06-storage-display.png        (1254脳1254, 2.02 MB)
   鈹斺攢鈹€ 07-trekking-pole-attachment.png (1254脳1254, 2.00 MB)
   ```

---

### 姝ラ2锛氫娇鐢╓ordPress REST API涓婁紶7寮犲浘鐗囧埌濯掍綋搴?
**璁よ瘉淇℃伅锛?*
- 鐢ㄦ埛鍚嶏細`AI1`
- Application Password锛歚yhY8qYGKo6tDsg1TIRoepeaO`
- Base64缂栫爜锛歚QUkxOnloWThxWUdLbzZ0RHNnMVRJUm9lcGVhTw==`

**涓婁紶鍛戒护锛?*
```powershell
$appId = "AI1"
$appPassword = "yhY8qYGKo6tDsg1TIRoepeaO"
$creds = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes("$appId`:$appPassword"))

# 鎵归噺涓婁紶7寮犲浘鐗?$images = @(
    @{Path="E:\AI\nuotao-ai-os\backpack-images\Nuotao_Backpack_Ecommerce_EN\01-main-image-black.png"; Title="Nuotao Lightweight Hiking Backpack Main Image"; Alt="nuotao lightweight hiking backpack 25l main product photo on white background"},
    @{Path="E:\AI\nuotao-ai-os\backpack-images\Nuotao_Backpack_Ecommerce_EN\02-color-options.png"; Title="Nuotao Backpack Color Options"; Alt="nuotao hiking backpack color options black green olive"},
    @{Path="E:\AI\nuotao-ai-os\backpack-images\Nuotao_Backpack_Ecommerce_EN\03-front-details.png"; Title="Nuotao Backpack Front Details"; Alt="nuotao hiking backpack front structure and pocket details"},
    @{Path="E:\AI\nuotao-ai-os\backpack-images\Nuotao_Backpack_Ecommerce_EN\04-back-panel-comfort.png"; Title="Nuotao Backpack Back Panel"; Alt="nuotao hiking backpack ergonomic shoulder straps and breathable back panel"},
    @{Path="E:\AI\nuotao-ai-os\backpack-images\Nuotao_Backpack_Ecommerce_EN\05-outdoor-lifestyle.png"; Title="Nuotao Backpack Outdoor Lifestyle"; Alt="nuotao hiking backpack outdoor lifestyle usage scene"},
    @{Path="E:\AI\nuotao-ai-os\backpack-images\Nuotao_Backpack_Ecommerce_EN\06-storage-display.png"; Title="Nuotao Backpack Storage Display"; Alt="nuotao hiking backpack storage capacity and organization pockets"},
    @{Path="E:\AI\nuotao-ai-os\backpack-images\Nuotao_Backpack_Ecommerce_EN\07-trekking-pole-attachment.png"; Title="Nuotao Backpack Trekking Pole Attachment"; Alt="nuotao hiking backpack trekking pole attachment display"}
)

foreach ($img in $images) {
    $response = curl.exe -s -X POST "https://nuotaooutdoor.com/wp-json/wp/v2/media" `
        -H "Authorization: Basic $creds" `
        -H "Accept: application/json" `
        -F "file=@$($img.Path);type=image/png" `
        -F "title=$($img.Title)" `
        -F "caption=$($img.Alt)"
    
    # 鎻愬彇Media ID
    if ($response -match '"id":(\d+)') {
        Write-Host "Media ID: $($matches[1])"
    }
}
```

**涓婁紶缁撴灉锛?*
| Media ID | 鏂囦欢鍚?| 灏哄 |
|----------|--------|------|
| 2610 | 01-main-image-black.png | 1254脳1254 |
| 2611 | 02-color-options.png | 1536脳1024 |
| 2612 | 03-front-details.png | 1254脳1254 |
| 2613 | 04-back-panel-comfort.png | 1254脳1254 |
| 2614 | 05-outdoor-lifestyle.png | 1254脳1254 |
| 2615 | 06-storage-display.png | 1254脳1254 |
| 2616 | 07-trekking-pole-attachment.png | 1254脳1254 |

---

### 姝ラ3锛氫娇鐢╓ooCommerce REST API鏇存柊浜у搧鍥剧墖

**璁よ瘉淇℃伅锛?*
- Consumer Key锛歚<1688_APP_KEY>`
- Consumer Secret锛歚<1688_APP_SECRET>`

**鏇存柊浜у搧鍥剧墖锛?*
```powershell
$productId = 2593
$consumerKey = "<1688_APP_KEY>"
$consumerSecret = "<1688_APP_SECRET>"
$base64Auth = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes("$consumerKey`:$consumerSecret"))

$images = @(
    @{id=2610},  # 涓诲浘
    @{id=2611},  # 鍥惧簱1
    @{id=2612},  # 鍥惧簱2
    @{id=2613},  # 鍥惧簱3
    @{id=2614},  # 鍥惧簱4
    @{id=2615},  # 鍥惧簱5
    @{id=2616}   # 鍥惧簱6
)

$body = @{
    id = $productId
    images = $images
} | ConvertTo-Json -Depth 10

$headers = @{
    "Authorization" = "Basic $base64Auth"
    "Content-Type" = "application/json"
    "Accept" = "application/json"
}

Invoke-RestMethod -Uri "https://nuotaooutdoor.com/wp-json/wc/v3/products/$productId" `
    -Method PUT -Headers $headers -Body $body -UseBasicParsing
```

---

### 姝ラ4锛氳缃浘鐗嘇lt Text

```powershell
$appId = "AI1"
$appPassword = "yhY8qYGKo6tDsg1TIRoepeaO"
$creds = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes("$appId`:$appPassword"))

$images = @(
    @{id=2610; alt="nuotao lightweight hiking backpack 25l main product photo on white background"},
    @{id=2611; alt="nuotao hiking backpack color options black green olive"},
    @{id=2612; alt="nuotao hiking backpack front structure and pocket details"},
    @{id=2613; alt="nuotao hiking backpack ergonomic shoulder straps and breathable back panel"},
    @{id=2614; alt="nuotao hiking backpack outdoor lifestyle usage scene"},
    @{id=2615; alt="nuotao hiking backpack storage capacity and organization pockets"},
    @{id=2616; alt="nuotao hiking backpack trekking pole attachment display"}
)

foreach ($img in $images) {
    $body = @{alt_text = $img.alt} | ConvertTo-Json
    Invoke-RestMethod -Uri "https://nuotaooutdoor.com/wp-json/wp/v2/media/$($img.id)" `
        -Method POST -Headers @{
            "Authorization" = "Basic $creds"
            "Content-Type" = "application/json"
            "Accept" = "application/json"
        } -Body $body -UseBasicParsing
}
```

---

### 楠岃瘉缁撴灉

```powershell
# 楠岃瘉浜у搧鍥剧墖宸叉洿鏂?$consumerKey = "<1688_APP_KEY>"
$consumerSecret = "<1688_APP_SECRET>"
$base64Auth = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes("$consumerKey`:$consumerSecret"))

$response = Invoke-RestMethod -Uri "https://nuotaooutdoor.com/wp-json/wc/v3/products/2593" `
    -Method GET -Headers @{"Authorization" = "Basic $base64Auth"; "Accept" = "application/json"} -UseBasicParsing

Write-Host "Product Images:"
foreach ($img in $response.images) {
    Write-Host "  - ID: $($img.id), Source: $($img.src)"
}
```

**楠岃瘉缁撴灉锛?*
- 鉁?7寮犲浘鐗囧凡涓婁紶鍒板獟浣撳簱锛圡edia ID: 2610-2616锛?- 鉁?浜у搧鍥剧墖宸叉洿鏂?- 鉁?Alt Text宸茶缃?- 鉁?浠锋牸锛?31.67锛堜繚鎸佷笉鍙橈級
- 鉁?搴撳瓨锛?00锛堜繚鎸佷笉鍙橈級
- 鉁?SKU锛歂T-NUOTAO-LIGHTW-1043302973575锛堜繚鎸佷笉鍙橈級

---

## 鎶€鏈鐐?
1. **WordPress REST API璁よ瘉**锛氫娇鐢ˋpplication Password鑰岄潪鐧诲綍瀵嗙爜
2. **WooCommerce REST API璁よ瘉**锛氫娇鐢–onsumer Key/Secret
3. **鍥剧墖鍛藉悕瑙勮寖**锛氫娇鐢ㄨ嫳鏂囨弿杩版€у悕绉帮紝渚夸簬SEO
4. **Alt Text瑙勮寖**锛氬寘鍚骇鍝佸悕绉般€侀鑹层€佺敤閫旂瓑鍏抽敭璇?
---

## 鐩稿叧鏂囦欢浣嶇疆

- 鍥剧墖婧愭枃浠讹細`E:\AI\nuotao-ai-os\backpack-images\Nuotao_Backpack_Ecommerce_EN\`
- 鍘熷ZIP锛歚C:\Users\绁為瓊涔嬩汉\Downloads\Nuotao_Backpack_Ecommerce_EN.zip`
