"""
浜у搧绔埌绔伐浣滄祦鏈嶅姟锛圥2-2锛?
涓茶仈閫夊搧鈫掍骇鍝佸垎鏋愨啋涓诲浘鐢熶骇鈫掔敓鍥綪rompt鈫掍笂鏋禬ooCommerce鐨勪竴閿祦杞€?
宸ヤ綔娴佹楠わ細
Step 1: 鍟嗗搧淇℃伅杈撳叆锛堜粠鐗涢】閫夊搧缁撴灉瀵煎叆鎴栨墜鍔ㄨ緭鍏ワ級
Step 2: AI浜у搧鍒嗘瀽锛?0瀛楁璇嗗埆 + 17瀛楁浜у搧鎶ュ憡锛?Step 3: 涓诲浘鐢熶骇锛?濂楁柟鍚?+ 鐭枃妗?+ 10涓彉浣擄級
Step 4: 鐢熷浘Prompt鐢熸垚锛堜富鍥綪rompt + 璇︽儏椤礟rompt锛?Step 5: 涓婃灦鏁版嵁鐢熸垚锛堝悕绉?鎻忚堪/浠锋牸/SKU/鍒嗙被/鏍囩锛?Step 6: 涓婃灦WooCommerce锛堝彲閫夛紝浜哄伐纭鍚庢墽琛岋級

閬靛惊AGENTS.md瑙勮寖锛?- 涓氬姟瑙勫垯闆嗕腑鍦ㄦ湇鍔″眰
- Agent绂佹鐩磋繛鏁版嵁搴擄紝閫氳繃services灞傝闂?- 鍏ㄩ摼璺彲瀹¤
- Human-in-the-loop锛氫笂鏋跺墠蹇呴』浜哄伐纭
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

from app.services.main_image_service import (
    run_complete_workflow as run_main_image_workflow,
)
from app.services.product_analysis_service import (
    analyze_and_generate_report,
)
from app.services.product_listing_service import (
    check_image_gate,
    is_restricted,
    list_to_woocommerce,
    map_category_to_wc,
    REQUIRED_MAIN_IMAGES,
    REQUIRED_DETAIL_IMAGES,
)
from app.services.product_content_service import normalize_image_urls
from app.services.product_readiness_gate import check_readiness, format_readiness_report
from app.services.prompt_generator_service import generate_full_prompt
from app.services.image_wc_pipeline import upload_images_to_wc, format_pipeline_report
from app.services.vision_image_quality_checker import (
    QualityResult,
    check_image_quality,
    format_quality_report,
)
from app.services.llm_gateway import LLMRequest, complete as llm_complete

logger = logging.getLogger(__name__)

# 鏈嶅姟閰嶇疆
SERVICE_NAME = "product_pipeline"
SERVICE_VERSION = "1.0.0"

# 宸ヤ綔娴佺姸鎬?PIPELINE_STATUS = {
    "PENDING": "pending",
    "RUNNING": "running",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "PARTIAL": "partial",
}

# 姝ラ瀹氫箟
PIPELINE_STEPS = [
    {"id": "input", "name": "鍟嗗搧淇℃伅杈撳叆", "description": "浠庣墰椤块€夊搧缁撴灉瀵煎叆鎴栨墜鍔ㄨ緭鍏ュ晢鍝佷俊鎭?},
    {"id": "analysis", "name": "AI浜у搧鍒嗘瀽", "description": "10瀛楁AI璇嗗埆 + 17瀛楁浜у搧淇℃伅鎶ュ憡"},
    {"id": "readiness", "name": "鏁版嵁灏辩华闂ㄧ", "description": "SOP Step 1.5: 妫€鏌ラ噸閲?灏哄/鏉愯川/鍏呯數鍙ｇ瓑涓婃灦鍏抽敭瀛楁瀹屾暣鎬?},
    {"id": "main_image", "name": "涓诲浘鐢熶骇", "description": "3濂椾富鍥炬柟鍚?+ 鐭枃妗?+ 10涓彉浣?},
    {"id": "prompt", "name": "鐢熷浘Prompt鐢熸垚", "description": "涓诲浘Prompt + 璇︽儏椤礟rompt"},
    {"id": "listing_data", "name": "涓婃灦鏁版嵁鐢熸垚", "description": "鍚嶇О/鎻忚堪/浠锋牸/SKU/鍒嗙被/鏍囩"},
    {"id": "v3_gate", "name": "V3.0閫夊搧闂搁棬", "description": "Nuotao Score 鍏淮璇勫垎 + V1-V12 涓€绁ㄥ惁鍐?+ 婕忔枟闃舵鍒ゅ畾"},
    {"id": "listing", "name": "涓婃灦WooCommerce", "description": "浜哄伐纭鍚庝笂鏋跺埌WooCommerce"},
]

# V3.0 闂搁棬鍒ゅ畾闃堝€硷細11 缁磋繍钀ュ垎瑕嗙洊鐜囦綆浜庢鍊兼椂锛屽鏁板搧鐗岀淮搴﹀彇鐨勬槸涓€?# 榛樿鍒嗭紝姝ゆ椂绠楀嚭鐨?Reject 绛夌骇鏄€屾暟鎹笉瓒炽€嶇殑浜х墿鑰岄潪鐪熷疄浣庡垎锛岃浆浜哄伐
# 澶嶆牳鑰屼笉鏄‖闃绘柇锛岄伩鍏嶉椄闂ㄥ湪缂烘暟鎹樁娈佃鏉€鍏ㄩ儴鍊欓€夈€?GATE_MIN_COVERAGE_RATIO = 0.30

# 闂搁棬涓夌缁撹锛歜locked 鏈変竴绁ㄥ惁鍐崇殑纭畾鎬ц瘉鎹紝蹇呴』闃绘柇涓婃灦锛沶eeds_review
# 鏃犲惁鍐充絾璇勫垎涓嶈冻浠ヨ嚜鍔ㄦ斁琛岋紱passed 鍙嚜鍔ㄦ斁琛屻€?GATE_BLOCKED = "blocked"
GATE_NEEDS_REVIEW = "needs_review"
GATE_PASSED = "passed"

# 婕忔枟闃舵鍙栧€硷紙涓?nuotao_selection_service 鍐欏叆 products.funnel_stage 涓€鑷达級銆?FUNNEL_REJECTED = "rejected"


class PipelineError(Exception):
    """宸ヤ綔娴佸紓甯?""


def get_pipeline_status() -> dict[str, Any]:
    """鑾峰彇宸ヤ綔娴佹湇鍔＄姸鎬?""
    return {
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "status": "operational",
        "steps": PIPELINE_STEPS,
        "statuses": PIPELINE_STATUS,
    }


def _safe_get(data: dict[str, Any], key: str, default: str = "") -> str:
    """瀹夊叏鑾峰彇瀛楀吀鍊?""
    value = data.get(key, default)
    if isinstance(value, list):
        return "銆?.join(str(v) for v in value)
    return str(value) if value else default


def _safe_get_list(data: dict[str, Any], key: str, default: list[str] | None = None) -> list[str]:
    """瀹夊叏鑾峰彇鍒楄〃鍊?""
    value = data.get(key, default or [])
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if value else (default or [])


def _generate_sku(
    product_name: str, category: str = "", offer_id: str | None = None
) -> str:
    """鐢熸垚绾?ASCII 鐨?SKU锛堣法澧冩笭閬撹姹傦細鏃犱腑鏂囥€佹棤绌烘牸銆佹棤绌烘锛夈€?
    瑙勫垯锛?
    - **鏈?1688 offer id**锛歚`NT-<offer_id>``銆傚畬鍏ㄧ敱鏉ユ簮鍐冲畾锛?*鍒绘剰涓嶅惈鏍囬璇?*
      鈥斺€旀爣棰樻潵鑷?LLM锛屾帾杈炰細婕傜Щ銆係KU 閲屼竴鏃︽幒杩涗細婕傜Щ鐨勬枃鏈紝鍚屼竴涓?offer 鍦?      涓嶅悓杩愯閲屽氨浼氬緱鍒颁笉鍚?SKU锛屼簬鏄?SKU 鏌ラ噸澶辨晥锛學ooCommerce 渚х殑 SKU 鍞竴鎬?      涔熸嫤涓嶄綇閲嶅寤哄晢鍝併€?    - **鏃?offer id**锛歚`NT-<鍏抽敭璇?-<MMDDHHMM>``銆傛病鏈夌ǔ瀹氭爣璇嗘椂鍙兘闈犳椂闂存埑锛?      姝ゆ椂淇濈暀鏍囬璇嶈嚦灏戣繕鏈夊彲璇绘€с€?
    闈?ASCII 瀛楃锛堝惈涓枃锛夋暣浣撳墧闄わ紱鑻ュ墧闄ゅ悗娌℃湁鍙敤鎷変竵璇嶏紙绾腑鏂囧悕锛夛紝閫€鍥炲埌
    鑻辨枃绫荤洰璇嶆垨 OUTDOOR锛屾渶鍚庣粺涓€娓呮礂杩炵画杩炲瓧绗︿笌绌烘锛屾潨缁濆弻杩炲瓧绗︺€?    """
    if offer_id:
        # 纭畾鎬?SKU锛氬悓涓€涓?1688 offer 姘歌繙鏄犲皠鍒板悓涓€涓?SKU锛屼笖涓?LLM 鏍囬鏃犲叧銆?        return f"NT-{offer_id}"

    # 鍙繚鐣?ASCII 瀛楁瘝/鏁板瓧锛屽叾浣欏叏閮ㄨ浆鎴愬垎闅旂
    ascii_only = re.sub(r"[^A-Za-z0-9]+", "-", product_name or "")
    tokens = [tok for tok in ascii_only.split("-") if tok]
    # 鍙栧墠涓や釜鏈夋剰涔夌殑鑻辨枃璇嶏紝姣忚瘝鏈€澶?6 瀛楃锛岄伩鍏嶈繃闀?    stop = {"THE", "AND", "FOR", "WITH", "HIGH", "BACK", "PORTABLE", "FOLDING", "CHAIR"}
    picked: list[str] = []
    for tok in tokens:
        up = tok.upper()
        if up in stop and picked:
            continue
        picked.append(up[:6])
        if len(picked) >= 2:
            break
    core = "-".join(picked) if picked else ""

    if not core:
        # 绾腑鏂囧悕绛夋棤鎷変竵璇嶅満鏅細鐢ㄨ嫳鏂囩被鐩垨鍥哄畾鍓嶇紑
        cat_ascii = re.sub(r"[^A-Za-z0-9]+", "-", category or "")
        cat_tokens = [t.upper()[:6] for t in cat_ascii.split("-") if t]
        core = "-".join(cat_tokens[:2]) if cat_tokens else "OUTDOOR"

    timestamp = datetime.now().strftime("%m%d%H%M")
    sku = f"NT-{core}-{timestamp}"
    # 鍏滃簳锛氬啀娆″帇缂╄繛缁繛瀛楃銆佸幓鎺夐灏捐繛瀛楃锛屼繚璇佹棤绌烘
    sku = re.sub(r"-+", "-", sku).strip("-")
    return sku


def _dedupe_real_image_urls(raw: Any) -> list[str]:
    """Flatten mixed image shapes to unique, publishable HTTP(S) URLs.

    Accepts plain strings or ``{"src"/"url"/"image_url": ...}`` entries.
    Anything that is not an absolute HTTP(S) URL is dropped rather than
    published: WooCommerce downloads listing images at sync time, so a
    ``data:`` URI, a local path or a mock placeholder cannot be delivered.
    The P0-3 mock backend's SVG placeholder is excluded by the same rule.
    """
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(
                item.get("src") or item.get("url") or item.get("image_url") or ""
            ).strip()
        else:
            continue
        if not text.startswith(("http://", "https://")):
            continue
        if text.lower().find("mock") >= 0:
            continue
        if text not in seen:
            seen.add(text)
            urls.append(text)
    return urls


def _collect_approved_media_urls(product_info: dict[str, Any]) -> list[str]:
    """Read approved creative assets written by ``attach_approved_image``.

    ``attach_approved_image`` stores approved, generated images under
    ``product.meta["media"]["images"]``. That location was never read when
    building listing data, so an approved real image could not satisfy the
    5-main + 6-detail image gate. The legacy flat keys are read as a
    fallback for backwards compatibility.
    """
    if not isinstance(product_info, dict):
        return []
    meta = product_info.get("meta")
    meta = meta if isinstance(meta, dict) else {}
    media = meta.get("media")
    media = media if isinstance(media, dict) else {}

    urls: list[str] = []
    for source in (media.get("images"), meta.get("main_images"), meta.get("images")):
        for url in _dedupe_real_image_urls(source):
            if url not in urls:
                urls.append(url)
    return urls


def _generate_listing_data(
    product_info: dict[str, Any],
    product_report: dict[str, Any],
    main_image_result: dict[str, Any],
) -> dict[str, Any]:
    """
    鐢熸垚涓婃灦鏁版嵁

    Args:
        product_info: 鍟嗗搧淇℃伅
        product_report: 浜у搧鎶ュ憡
        main_image_result: 涓诲浘鐢熶骇缁撴灉

    Returns:
        涓婃灦鏁版嵁
    """
    # 浜у搧鍚嶇О锛堜紭鍖栧悗鐨勭數鍟嗗悕绉帮級
    product_name = _safe_get(product_report, "product_name", _safe_get(product_info, "name", "浜у搧"))

    # 浜у搧鎻忚堪锛堥暱鎻忚堪锛?    product_description = _safe_get(product_report, "product_description", "")
    if not product_description:
        # 浠庡崠鐐瑰拰鍔熻兘鎷兼帴鎻忚堪
        selling_points = _safe_get_list(product_report, "core_selling_points", [])
        features = _safe_get_list(product_report, "product_features", [])
        desc_parts = []
        if selling_points:
            desc_parts.append("銆愭牳蹇冨崠鐐广€慭n" + "\n".join(f"鈥?{sp}" for sp in selling_points))
        if features:
            desc_parts.append("銆愪骇鍝佸姛鑳姐€慭n" + "\n".join(f"鈥?{f}" for f in features))
        product_description = "\n\n".join(desc_parts)

    # 鐭弿杩?    short_description = _safe_get(product_info, "description", "")
    if not short_description:
        short_description = product_description[:100] + "..." if len(product_description) > 100 else product_description

    # 浠锋牸锛堜粠1688浠锋牸鎺ㄧ畻锛屼娇鐢?Nuotao 瀹氫环绛栫暐锛?    # 绛栫暐锛氶噰璐环(CNY) / 姹囩巼 脳 鍊嶆暟 = 缇庡厓鍞环
    # 榛樿姹囩巼 7.2锛岄粯璁ゅ€嶆暟 6.0锛堜繚璇佸叏鎴愭湰鍒╂鼎鐜?> 60%锛?    PRICE_MARKUP_MULTIPLIER = float(_safe_get(product_info, "price_markup", "6.0"))
    USD_CNY_RATE = float(_safe_get(product_info, "usd_cny_rate", "7.2"))

    price_str = _safe_get(product_info, "price", "")
    regular_price = ""
    try:
        import re
        price_match = re.search(r'[\d.]+', price_str)
        if price_match:
            source_price_cny = float(price_match.group())
            # CNY 鈫?USD锛屽啀涔樹互瀹氫环鍊嶆暟
            regular_price = f"{source_price_cny / USD_CNY_RATE * PRICE_MARKUP_MULTIPLIER:.2f}"
            logger.info(
                "Price calculated: CNY %.2f / %.2f * %.1f = USD %s",
                source_price_cny, USD_CNY_RATE, PRICE_MARKUP_MULTIPLIER, regular_price,
            )
    except Exception:
        pass

    # SKU锛氭湁 1688 offer id 鏃剁敤纭畾鎬?SKU锛屽悓涓€涓摼鎺ヤ笉浼氬洜瀵煎叆鏃堕棿涓嶅悓鑰屾崲 SKU銆?    from app.services.product_source_identity import resolve_source_offer_id

    sku = _generate_sku(
        product_name,
        offer_id=resolve_source_offer_id(
            source_url=_safe_get(product_info, "source_url", ""),
            source_id=_safe_get(product_info, "source_id", ""),
            meta=product_info if isinstance(product_info, dict) else None,
        ),
    )

    # 鍒嗙被锛氭寜鍟嗗搧鍚?+ 鍐呴儴绫荤洰鏄犲皠鍒?WooCommerce 鐪熷疄鍒嗙被 term id
    # 锛堟棫閫昏緫纭紪鐮佸唴閮?id 15锛屾伆濂界瓑浜?WC 鐨?Uncategorized锛屽鑷村叏閮ㄥ綊鍒版湭鍒嗙被锛?    category = _safe_get(product_info, "category", "")
    categories = map_category_to_wc(product_name, category)

    # 鏍囩锛氫繚鐣欏畬鏁存枃鏈€傛棫瀹炵幇鎴柇鍒?10 瀛楃锛屼腑鏂囨爣绛惧叆搴撳嵆娈嬬己锛?    # 鐩存帴褰卞搷 WooCommerce 绔悳绱笌杩囨护锛涢暱搴︿笂闄愭斁瀹藉埌 60 瀛楃闃叉瀬绔暱鍙ャ€?    tags = []
    selling_points = _safe_get_list(product_report, "core_selling_points", [])
    for sp in selling_points[:3]:
        tags.append({"name": sp.strip()[:60]})
    usage_scenarios = _safe_get_list(product_report, "usage_scenarios", [])
    for scenario in usage_scenarios[:2]:
        tags.append({"name": scenario.strip()[:60]})

    # 涓婃灦浼樺厛浣跨敤宸插鍏ョ殑 1688 鍘熷浘锛汚I 鐢熷浘缁撴灉闇€瀹℃牳鍚庡啓鍥炲晢鍝佸獟浣撳瓧娈点€?    # A-3 fix (2026-09-18): 鎶婂浘鐗囨媶鎴?main_images / detail_images 涓や釜瀛楁锛?    # 涓?check_image_gate 鐨勪富鍥?5 + 璇︽儏鍥?6 璇箟瀵归綈銆?688 鍘熷浘榛樿褰掑叆
    # main_images锛堝彇鍓?5 寮狅級锛宒etail_images 鐣欑┖鐢辨壒閲忕敓鍥惧～鍏咃紱
    # images 淇濈暀鎵佸钩鍚堝苟鏁扮粍鍋氬悜鍚庡吋瀹癸紙WC API 涓庢棫鍓嶇浠嶈姝ゅ瓧娈碉級銆?    # P0-6: 宸插鎵圭殑 Creative Asset 鐢?attach_approved_image 鍐欏叆
    # product.meta["media"]["images"]锛屾鍓嶄粠鏈繘鍏?listing data锛屽鑷?    # check_image_gate 鐨?5+6 闂ㄧ姘歌繙鏃犳硶閫氳繃銆傚鎵瑰悗鐨勭湡瀹炲浘鐗囩幇鍦ㄥ苟鍏?    # 鍥剧墖闆嗭紙1688 鍘熷浘鍦ㄥ墠锛屼繚鎸佸師鏈夋帓搴忥級锛屼笖鍏ㄩ儴杩囨护涓哄彲鎶撳彇鐨勭湡瀹?    # HTTP(S) URL 鈥斺€?data: URI / mock 鍗犱綅鍥?/ 鏈湴璺緞涓€寰嬩涪寮冦€?    approved_images = _collect_approved_media_urls(product_info)
    all_1688_images = [
        {"src": url}
        for url in _dedupe_real_image_urls(product_info.get("images"))
    ]

    # BUG #5 fix: 鍚堝苟 AI 鐢熸垚鍥剧墖銆傝法鏉ユ簮鍏ㄥ眬鍘婚噸 鈥斺€?鍚屼竴 URL 鍑虹幇鍦?    # 1688 鍘熷浘涓庣敓鎴愮粨鏋滀腑鏃跺彧淇濈暀棣栨鍑虹幇锛岄伩鍏?WC 閲嶅鍥剧墖涓庤櫄澧炶鏁般€?    generated_images: list[dict[str, str]] = []
    if isinstance(main_image_result, dict):
        generated_images = [
            {"src": url}
            for url in _dedupe_real_image_urls(main_image_result.get("generated_images"))
        ]

    all_images = []
    seen_urls: set[str] = set()
    for image in [*all_1688_images, *generated_images]:
        if image["src"] in seen_urls:
            continue
        seen_urls.add(image["src"])
        all_images.append(image)
    for url in approved_images:
        if url in seen_urls:
            continue
        seen_urls.add(url)
        all_images.append({"src": url})

    main_images = all_images[:5]  # 鏈€澶氬彇 5 寮犱綔涓轰富鍥?    detail_images: list[dict[str, str]] = all_images[5:]  # 鍓╀綑浣滀负璇︽儏鍥?    images = main_images + detail_images  # 鎵佸钩鍚堝苟锛屽悜鍚庡吋瀹?
    logger.info(
        "Listing: %d 1688 + %d generated + %d approved = %d total",
        len(all_1688_images), len(generated_images),
        len(approved_images), len(all_images),
    )

    return {
        "name": product_name,
        "type": "simple",
        "regular_price": regular_price,
        "description": product_description,
        "short_description": short_description,
        "sku": sku,
        "manage_stock": True,
        "stock_quantity": 100,  # 榛樿搴撳瓨
        "status": "draft",  # 榛樿鑽夌锛屼汉宸ョ‘璁ゅ悗鍙戝竷
        "categories": categories,
        "tags": tags,
        "images": images,
        "main_images": main_images,
        "detail_images": detail_images,
        "meta_data": [
            {"key": "source", "value": "1688"},
            {"key": "source_price", "value": price_str},
            {"key": "pricing_formula", "value": f"CNY {price_str} / {USD_CNY_RATE} 脳 {PRICE_MARKUP_MULTIPLIER} = USD {regular_price}" if regular_price else ""},
            {"key": "pipeline_id", "value": str(uuid.uuid4())},
        ],
    }




# 鐩爣甯傚満榛樿缇庡浗鈥斺€斾笂鏋?WooCommerce 鐨勫晢鍝佹枃妗堝繀椤讳负鑻辨枃銆?# 璇ュ嚱鏁版妸 Step 5 鐢熸垚鐨勪腑鏂?涓嫳娣锋帓 listing 浜ょ粰 LLM 鍋氫竴娆¤嫳鏂囨湰鍦板寲锛?# 澶辫触鏃堕檷绾т繚鐣欏師鏂囧苟鍦?warnings 閲屾爣娉紝涓嶉樆濉炰富娴佺▼銆?def _has_cjk(text: str) -> bool:
    """绮楀垽鏂囨湰鏄惁鍚腑鏂囧瓧绗︺€?""
    if not text:
        return False
    return any('\u4e00' <= ch <= '\u9fff' for ch in text)


async def _english_localize_listing_data(listing_data: dict[str, Any]) -> dict[str, Any]:
    """鎶婁笂鏋舵暟鎹腑鐨?name / short_description / description / tags 鏈湴鍖栧埌鑻辨枃銆?""
    try:
        name = listing_data.get("name", "") or ""
        short_desc = listing_data.get("short_description", "") or ""
        long_desc = listing_data.get("description", "") or ""
        tags = [t.get("name", "") for t in listing_data.get("tags", []) if isinstance(t, dict)]

        # 涓嶉渶瑕佹湰鍦板寲灏辫烦杩?        if not (_has_cjk(name) or _has_cjk(short_desc) or _has_cjk(long_desc)
                 or any(_has_cjk(t) for t in tags)):
            listing_data.setdefault("_localization", {"status": "skipped", "reason": "no CJK content"})
            return listing_data

        prompt = (
            "You are an e-commerce localization expert for a US outdoor gear DTC brand. "
            "Translate and adapt the following Chinese product listing into natural, SEO-friendly "
            "American English. Keep brand names and model names as-is ONLY if they are already in Latin characters. "
            "If any Chinese characters appear in brand names, TRANSLATE them to English. "
            "Do NOT add marketing fluff not supported by the source. "
            "Return ONLY a JSON object with keys: "
            "name (max 80 chars, NO Chinese characters allowed), "
            "short_description (max 300 chars plain text, NO Chinese characters), "
            "description (HTML allowed, 200-600 words, NO Chinese characters), "
            "tags (array of 5-8 short English keywords).\n\n"
            f"SOURCE_NAME: {name}\n"
            f"SOURCE_SHORT: {short_desc}\n"
            f"SOURCE_LONG: {long_desc}\n"
            f"SOURCE_TAGS: {', '.join(tags)}\n"
        )

        resp = await llm_complete(
            LLMRequest(
                messages=[{"role": "user", "content": prompt}],
                task_type="listing_localization",
                temperature=0.3,
                max_tokens=1500,
                response_format="json_object",
            ),
        )
        import json as _json
        localized = _json.loads(resp.content)

        if isinstance(localized, dict):
            # === 缈昏瘧鍚庨獙璇侊細纭繚娌℃湁涓枃娈嬬暀 ===
            localized_name = str(localized.get("name", ""))[:120]
            localized_short = str(localized.get("short_description", ""))[:500]
            localized_long = str(localized.get("description", ""))
            localized_tags = localized.get("tags", [])

            # 妫€鏌ョ炕璇戠粨鏋滄槸鍚﹁繕鏈変腑鏂?            if _has_cjk(localized_name):
                logger.warning("Localized name still contains CJK: %s", localized_name)
                # 灏濊瘯绉婚櫎涓枃锛屽彧淇濈暀 ASCII 瀛楃
                localized_name = re.sub(r'[\u4e00-\u9fff]+', '', localized_name).strip()
                # 濡傛灉绉婚櫎鍚庝负绌猴紝浣跨敤鍘熷鍚嶇О鐨?ASCII 閮ㄥ垎
                if not localized_name:
                    localized_name = re.sub(r'[^A-Za-z0-9\s\-]', '', name).strip()[:120]

            if _has_cjk(localized_short):
                logger.warning("Localized short_description still contains CJK")
                localized_short = re.sub(r'[\u4e00-\u9fff]+', '', localized_short).strip()

            if _has_cjk(localized_long):
                logger.warning("Localized description still contains CJK")
                localized_long = re.sub(r'[\u4e00-\u9fff]+', '', localized_long).strip()

            if isinstance(localized_tags, list) and localized_tags:
                # 杩囨护鎺夊寘鍚腑鏂囩殑鏍囩
                localized_tags = [t for t in localized_tags if not _has_cjk(str(t))]

            # 搴旂敤缈昏瘧缁撴灉
            if localized_name:
                listing_data["name"] = localized_name
                # 鑻辨枃鏍囬纭畾鍚庯紝閲嶆柊鐢熸垚绾?ASCII SKU锛岃鐩?Step5 鍩轰簬涓枃鍚嶇敓鎴愮殑 SKU
                try:
                    from app.services.product_source_identity import (
                        resolve_source_offer_id,
                    )

                    offer_id = resolve_source_offer_id(
                        source_url=str(listing_data.get("source_url") or ""),
                        meta=listing_data if isinstance(listing_data, dict) else None,
                    )
                    if offer_id:
                        listing_data["sku"] = _generate_sku(
                            listing_data["name"],
                            listing_data.get("categories_label", ""),
                            offer_id=offer_id,
                        )
                    else:
                        old_sku = str(listing_data.get("sku") or "")
                        ts_match = re.search(r"(\d{6,})$", old_sku)
                        new_sku = _generate_sku(
                            listing_data["name"], listing_data.get("categories_label", "")
                        )
                        if ts_match:
                            new_sku = re.sub(r"\d{6,}$", ts_match.group(1), new_sku)
                        listing_data["sku"] = new_sku
                except Exception:  # noqa: BLE001
                    pass

            if localized_short:
                listing_data["short_description"] = localized_short
            if localized_long:
                listing_data["description"] = localized_long
            if isinstance(localized_tags, list) and localized_tags:
                listing_data["tags"] = [{"name": str(t)[:80]} for t in localized_tags[:10]]

            listing_data.setdefault("_localization", {
                "status": "localized",
                "provider": resp.provider,
                "model": resp.model,
            })
        else:
            listing_data.setdefault("_localization", {"status": "degraded", "reason": "LLM returned non-object"})
    except Exception as e:  # noqa: BLE001
        logger.warning("English localization failed, keeping source text: %s", e)
        listing_data.setdefault("_localization", {"status": "failed", "reason": str(e)[:300]})
    return listing_data


# 涓诲浘鏂瑰悜 鈫?鑻辨枃鑳屾櫙/鐢婚潰鎻忚堪锛堢敓鍥?prompt 蹇呴』鑻辨枃鍖栵紝涓讳綋涓嶅厑璁镐繚鐣欎腑鏂囧悕锛?_EN_BG_BY_KEY: dict[str, str] = {
    "white_background": "pure white background, clean and minimal e-commerce studio shot, soft even lighting, product centered",
    "real_scene": "realistic outdoor lifestyle scene in nature, natural daylight, immersive usage context, product clearly visible",
    "promotion_conversion": "vibrant promotional background with strong visual impact, sale campaign mood, bold composition",
}
_EN_BG_BY_NAME: dict[str, str] = {
    "鐧藉簳娓呯埥": _EN_BG_BY_KEY["white_background"],
    "鐪熷疄鍦烘櫙": _EN_BG_BY_KEY["real_scene"],
    "淇冮攢杞寲": _EN_BG_BY_KEY["promotion_conversion"],
}


def _english_subject_prompt(english_name: str) -> str:
    return f"{english_name}, premium quality, accurate product appearance, high detail, e-commerce product photography"


def localize_main_image_prompts(main_image_data: dict[str, Any], english_name: str) -> dict[str, Any]:
    """鎶婁富鍥剧敓浜х粨鏋滈噷鐢ㄤ簬鐢熷浘鐨勬柟鍚?prompt 涓讳綋/鑳屾櫙鏀瑰啓涓鸿嫳鏂囥€?
    Step3 涓诲浘鐢熶骇鍦?Step5 鑻辨枃鍖栦箣鍓嶈繍琛岋紝鏂瑰悜 prompt 鐨勪富浣撳師鏈槸涓枃鍚嶃€?    鍦ㄦ嬁鍒拌嫳鏂?listing 鏍囬鍚庡洖濉紝淇濊瘉鏈€缁堥€佽繘鐢熷浘妯″瀷鐨?prompt 鍏ㄨ嫳鏂囥€?    灏卞湴鏇存柊骞惰繑鍥?main_image_data銆?    """
    if not main_image_data or not english_name:
        return main_image_data
    subject_en = _english_subject_prompt(english_name)
    try:
        # 1) 椤跺眰鎵佸钩 directions 鏁扮粍锛堝墠绔洿鎺ヨ鍙?鐢ㄤ簬鐢熷浘锛?        for d in main_image_data.get("directions", []) or []:
            if not isinstance(d, dict):
                continue
            bg_en = _EN_BG_BY_NAME.get(str(d.get("name", ""))) or _EN_BG_BY_KEY["white_background"]
            d["prompt"] = f"Subject: {subject_en} | Background: {bg_en}"
            prompt_block = d.get("prompt")
        # 2) 搴曞眰 step02 涓夋柟鍚戠粨鏋?        workflow = main_image_data.get("workflow", {}) or {}
        step02 = workflow.get("step02_three_directions", {}) or {}
        for key, d in (step02.get("directions", {}) or {}).items():
            if not isinstance(d, dict):
                continue
            bg_en = _EN_BG_BY_KEY.get(key, _EN_BG_BY_KEY["white_background"])
            p = d.get("prompt")
            if isinstance(p, dict):
                p["subject"] = subject_en
                p["background"] = bg_en
        if main_image_data.get("product_name"):
            main_image_data["product_name"] = english_name
    except Exception as e:  # noqa: BLE001
        logger.warning("Localize main image prompts failed (non-blocking): %s", e)
    return main_image_data


def evaluate_v3_gate(evaluation: dict[str, Any]) -> dict[str, Any]:
    """鎶婁竴娆?V3.0 璇勪及缁撴灉鍒ゅ畾涓洪椄闂ㄧ粨璁猴紙绾嚱鏁帮紝鏃犲壇浣滅敤锛夈€?
    闂搁棬鍙銆屾湁涓€绁ㄥ惁鍐崇‘瀹氭€ц瘉鎹€嶇殑浜у搧纭樆鏂€傝瘎鍒嗙瓑绾т负 Reject 浣?11 缁?    瑕嗙洊鐜囦笉瓒虫椂锛屽鏁扮淮搴﹀彇鐨勬槸涓€ч粯璁ゅ垎锛岃繖绉?Reject 鏄暟鎹己澶辩殑浜х墿鑰岄潪
    鐪熷疄浣庡垎锛屾寜 needs_review 浜や汉宸ュ鐞嗭紝涓嶈兘鎹璇潃鍊欓€?    锛坉ocs/nuotao_product_score_v3.0.md 搂2.3銆伮?锛夈€?    """
    veto = evaluation.get("veto") or {}
    failed = [str(item) for item in (veto.get("failed") or [])]
    pending = [str(item) for item in (veto.get("pending") or [])]
    grade = evaluation.get("grade")
    total = evaluation.get("nuotao_total")
    coverage = (evaluation.get("evidence") or {}).get("operational_v2_coverage") or {}
    coverage_ratio = coverage.get("coverage_ratio")

    if failed:
        verdict = GATE_BLOCKED
        reason = f"瑙﹀彂涓€绁ㄥ惁鍐筹細{'銆?.join(failed)}"
    elif grade == "reject" and (
        coverage_ratio is None or float(coverage_ratio) < GATE_MIN_COVERAGE_RATIO
    ):
        verdict = GATE_NEEDS_REVIEW
        reason = (
            f"Nuotao Score {total} 涓?Reject锛屼絾 11 缁磋繍钀ュ垎瑕嗙洊鐜囦粎 {coverage_ratio}"
            f"锛堥槇鍊?{GATE_MIN_COVERAGE_RATIO}锛夛紝澶氭暟缁村害涓轰腑鎬ч粯璁ゅ垎锛?
            "闇€琛ュ叏鎴愭湰/渚涘簲鍟嗙瓑鏁版嵁鍚庨噸璇勶紝鎴栦汉宸ュ鏍告斁琛?
        )
    elif grade == "reject":
        verdict = GATE_NEEDS_REVIEW
        reason = f"Nuotao Score {total} 浣庝簬 65锛圧eject 绛夌骇锛夛紝涓嶅缓璁笂鏋?
    else:
        verdict = GATE_PASSED
        reason = f"鏃犱竴绁ㄥ惁鍐筹紝Nuotao Score {total}锛坽grade}锛?

    return {
        "verdict": verdict,
        "reason": reason,
        "blocked": verdict == GATE_BLOCKED,
        "auto_list_allowed": verdict == GATE_PASSED,
        "nuotao_total": total,
        "grade": grade,
        "funnel_stage": evaluation.get("funnel_stage"),
        "veto_failed": failed,
        "veto_pending": pending,
        "coverage_ratio": coverage_ratio,
    }


async def check_product_push_gate(
    session: AsyncSession,
    product_id: str,
    *,
    workspace_id: UUID | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """涓婃灦鎺ㄩ€佸墠鐨?V3.0 闂搁棬妫€鏌ワ紙瀵瑰凡钀藉簱鍟嗗搧锛夈€?
    涓?run_v3_gate 鐨勫尯鍒細閭ｉ噷涓烘祦姘寸嚎闃舵鐨勫晢鍝佸缓妗ｅ苟璇勪及锛岃繖閲岀洿鎺ヨ瘎浼?    鏃㈡湁 Product 琛岋紝鐢ㄤ簬娓犻亾涓庝笂鏋堕〉鐨勬帹閫侀€氶亾锛坉ocs/sop_audit_selection_to_
    listing.md 搂3.1 璁板綍鐨勩€岄€氶亾鈶¤８濂斻€嶏級銆?
    鍒ゅ畾瑙勫垯锛?    - blocked锛堣Е鍙戜竴绁ㄥ惁鍐筹級锛氱‖闃绘柇锛宖orce 涔熶笉鏀捐锛?    - needs_review锛堜綆鍒?/ 瑕嗙洊鐜囦笉瓒?/ 璇勪及澶辫触锛夛細闇€浜哄伐鏄惧紡纭鍚?force 鏀捐锛?      绗﹀悎 AGENTS.md 3.1銆孉I 鍙缓璁€佸叧閿姩浣滀汉瀹°€嶏紱
    - passed锛氱洿鎺ユ斁琛屻€?
    璇勪及寮傚父锛圠LM 缃戝叧涓嶅彲鐢ㄧ瓑锛夋寜 needs_review 澶勭悊锛岀粷涓嶉潤榛樻斁琛屻€?    """
    from app.core.workspace import DEFAULT_WORKSPACE_ID
    from app.models.product import Product
    from app.services.nuotao_selection_service import evaluate_product

    workspace_id = workspace_id or DEFAULT_WORKSPACE_ID
    product = (
        await session.execute(select(Product).where(Product.id == product_id))
    ).scalar_one_or_none()
    if product is None:
        return {
            "verdict": GATE_NEEDS_REVIEW,
            "blocked": True,
            "force_required": True,
            "reason": f"浜у搧涓嶅瓨鍦? {product_id}",
        }

    try:
        evaluation = await evaluate_product(
            session, product.id, workspace_id=workspace_id,
        )
        gate = evaluate_v3_gate(evaluation)
    except Exception as e:  # noqa: BLE001
        # 璇勪及涓嶅彲鐢ㄦ椂涓嶉樆鏂篃涓嶆斁琛岋紝杞汉宸ョ‘璁?        logger.warning(
            "V3.0 闂搁棬璇勪及澶辫触锛岃浆浜哄伐纭: product=%s, error=%s", product_id, e
        )
        return {
            "verdict": GATE_NEEDS_REVIEW,
            "blocked": False,
            "force_required": True,
            "reason": f"V3.0 閫夊搧闂搁棬璇勪及澶辫触锛坽e}锛夛紝闇€浜哄伐澶嶆牳纭鍚庣户缁?,
            "product_id": str(product.id),
            "sku": product.sku,
        }

    gate["product_id"] = str(product.id)
    gate["sku"] = product.sku
    gate["blocked"] = bool(gate["blocked"])
    gate["force_required"] = (gate["verdict"] == GATE_NEEDS_REVIEW) and not force
    return gate


def _parse_weight_kg(raw: Any) -> Decimal | None:
    """浠?'500g' / '0.5kg' / '1.2 鍗冨厠' 瑙ｆ瀽鍏枻鏁帮紱瑙ｆ瀽涓嶅嚭杩斿洖 None銆?""
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        return raw
    matches = re.findall(
        r"(\d+(?:\.\d+)?)\s*(kg|kgs|鍗冨厠|鍏枻|g|鍏??", str(raw).strip().lower()
    )
    if not matches:
        return None
    unit = next((m[1] for m in reversed(matches) if m[1]), "kg")
    # ROUND-4D: 鑼冨洿鍊硷紙濡?"1462-2100g"锛夋寜涓婄晫璁¤垂锛屽彇棣栨暟瀛椾細浣庝及杩愯垂銆?    # 浠呭湪鏄庣‘鐨勬暟瀛?鏁板瓧鑼冨洿鍐呭彇涓婄晫锛岄伩鍏嶈浼?"1800g 鍨嬪彿X2" 杩欑被鍊笺€?    text = str(raw).strip().lower()
    try:
        if re.search(r"\d\s*[-~鈥撯€擼\s*\d", text):
            value = max(Decimal(m[0]) for m in matches)
        else:
            value = Decimal(matches[0][0])
    except (ArithmeticError, ValueError):
        return None
    return (value / Decimal("1000")).quantize(Decimal("0.001")) if unit in ("g", "鍏?) else value


def _parse_decimal(raw: Any) -> Decimal | None:
    """浠?'楼6.7' / '6.7-19.7' 鍙栫涓€涓暟鍊硷紱鍙栦笉鍒拌繑鍥?None銆?""
    if raw is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(raw))
    if not match:
        return None
    try:
        return Decimal(match.group())
    except (ArithmeticError, ValueError):
        return None


async def run_v3_gate(
    session: AsyncSession,
    product_info: dict[str, Any],
    listing_data: dict[str, Any],
    *,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """钀藉簱鍊欓€変骇鍝佸苟鎵ц V3.0 璇勪及锛岃繑鍥為椄闂ㄧ粨璁恒€?
    娴佹按绾块樁娈典骇鍝佸皻鏈惤搴擄紝鑰?V3.0 璇勪及浠?Product 琛屼负杈撳叆锛屽洜姝ら椄闂ㄥ厛鐢ㄤ笂鏋?    鏁版嵁鍒涘缓 candidate 琛岋紙鍚?SKU 宸插瓨鍦ㄥ垯澶嶇敤锛岄伩鍏嶉噸澶嶅缓妗ｏ級锛屽啀璇勪及銆備骇鍝佺敱
    姝よ繘鍏?V3.0 婕忔枟锛屽悗缁彲鍦ㄥ€欓€夐〉琛ュ叏鎴愭湰/渚涘簲鍟嗘暟鎹噸璇勩€?
    闂搁棬涓嶄吉閫犳垚鏈暟鎹細娴佹按绾块樁娈垫病鏈夌湡瀹炶惤鍦版垚鏈紝瀹佺己鍕块€狅紝鍥犳涓嶅啓
    ProductCost锛孷9/V10 淇濇寔 pending锛圓GENTS.md 搂1.2.5銆伮?.1 鏄惧紡绌哄€煎鐞嗭級銆?    """
    from app.core.workspace import DEFAULT_WORKSPACE_ID
    from app.models.product import Product
    from app.services.nuotao_selection_service import evaluate_product
    from app.services.product_source_identity import (
        get_or_create_by_source,
        resolve_source_offer_id,
    )

    workspace_id = workspace_id or DEFAULT_WORKSPACE_ID
    # 鏉ユ簮閿厛绠楀嚭鏉ワ細SKU 鐢熸垚涓庡箓绛夊缓妗ｉ兘瑕佺敤瀹冦€?    source_offer_id = resolve_source_offer_id(
        source_url=product_info.get("source_url"),
        source_id=product_info.get("source_id"),
        meta=product_info if isinstance(product_info, dict) else None,
    )
    # 鏈夋潵婧愰敭鏃?SKU 鐢?offer id 纭畾鎬ф淳鐢燂紱listing_data 宸插甫 SKU 鍒欐部鐢ㄣ€?    sku = str(
        listing_data.get("sku")
        or _generate_sku(str(listing_data.get("name") or ""), offer_id=source_offer_id)
    )
    name = str(listing_data.get("name") or product_info.get("name") or "鏈懡鍚嶅晢鍝?)

    source_price = _parse_decimal(product_info.get("price"))
    sale_price = _parse_decimal(listing_data.get("regular_price"))
    meta = {
        "source": "product_pipeline",
        "source_url": product_info.get("source_url") or None,
        "source_id": product_info.get("source_id") or None,
        "source_price": str(source_price) if source_price is not None else None,
        "sale_price": str(sale_price) if sale_price is not None else None,
        "pipeline_trace_id": trace_id,
    }

    # 銆屽悓涓€涓?1688 閾炬帴鍙兘鏈変竴鏉℃椿鍊欓€夈€嶇敱 source_offer_id 淇濊瘉锛屼笉鍐嶅彧闈?SKU銆?
    def _build_candidate() -> Product:
        return Product(
            workspace_id=workspace_id,
            sku=sku,
            name=name,
            description=str(listing_data.get("short_description") or "")[:2000] or None,
            category=product_info.get("category") or None,
            status="draft",
            candidate_status="candidate",
            source="1688" if product_info.get("source_url") else "pipeline",
            source_url=product_info.get("source_url") or None,
            source_offer_id=source_offer_id,
            weight_kg=_parse_weight_kg(product_info.get("weight")),
            target_market=str(product_info.get("target_market") or "US"),
            meta=meta,
        )

    product, created = await get_or_create_by_source(
        session,
        workspace_id=workspace_id,
        source_offer_id=source_offer_id,
        build=_build_candidate,
        fallback_sku=sku,
    )
    if not created:
        # 鍛戒腑宸叉湁鍊欓€夛紙鎸夋潵婧愰敭鎴栧巻鍙?SKU锛夛細鍚屾鏈杩愯鐨勬渶鏂颁俊鎭紝涓嶉噸澶嶅缓妗ｃ€?        product.name = name
        product.category = product.category or product_info.get("category") or None
        product.meta = {
            **(product.meta or {}),
            **{key: value for key, value in meta.items() if value is not None},
        }
        if product.weight_kg is None:
            product.weight_kg = _parse_weight_kg(product_info.get("weight"))

    # BUG-13 (2026-09-20): listing_data already carries the media and taxonomy
    # this pipeline produced - 1688 originals + AI-generated images, tags - and
    # product_info carries the parsed weight / dimensions / attributes. None of
    # it was persisted here, so every product reached the store without a main
    # image, tags or attributes. listing_data only went back to the caller in
    # the pipeline result; it never reached the product row.
    from sqlalchemy.orm.attributes import flag_modified
    from app.services.listing_gate import (
        collect_attributes,
        normalise_listing_images,
        normalise_listing_tags,
        parse_dimensions,
    )

    listing_media = normalise_listing_images(
        listing_data.get("main_images") or listing_data.get("images")
    )
    listing_tag_names = normalise_listing_tags(listing_data.get("tags"))
    listing_attrs = collect_attributes(product_info)
    listing_dims = parse_dimensions(product_info.get("dimensions"))

    if listing_media and not (product.meta or {}).get("main_images"):
        product.meta = {**(product.meta or {}), "main_images": listing_media}
    if listing_tag_names and not product.tags:
        product.tags = listing_tag_names
    if listing_attrs and not product.attributes:
        product.attributes = listing_attrs
    if listing_dims and not product.dimensions:
        product.dimensions = listing_dims

    # The products JSON columns are plain JSON with no MutableDict, so plain
    # reassignment is not reliably flushed. Flag each column we actually touched
    # - this is the pattern that verifiably persisted in production.
    if listing_media:
        flag_modified(product, "meta")
    if listing_tag_names:
        flag_modified(product, "tags")
    if listing_attrs:
        flag_modified(product, "attributes")
    if listing_dims:
        flag_modified(product, "dimensions")
    if product.weight_kg is None:
        product.weight_kg = _parse_weight_kg(product_info.get("weight"))

    await session.flush()

    evaluation = await evaluate_product(
        session, product.id, workspace_id=workspace_id, trace_id=trace_id
    )
    gate = evaluate_v3_gate(evaluation)
    gate["product_id"] = str(product.id)
    gate["sku"] = sku
    gate["dimensions"] = evaluation.get("dimensions")
    await session.flush()
    return gate


async def _remember_listed_product(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    sku: str | None,
    wc_id: Any,
) -> None:
    """涓婃灦鎴愬姛鍚庢妸 WooCommerce 鍟嗗搧 ID 鍐欏洖鏈湴涓绘暟鎹紙骞傜瓑锛夈€?
    Step 7 ``auto_list`` 姝ゅ墠**涓嶅洖鍐?*锛氬彧鏈?``/product-pipeline/confirm-list`` 浼氶€氳繃
    ``upsert_local_listed_product`` 鍐欍€備簬鏄繖鏉¤矾寰勪笂鏋剁殑鏈湴鍟嗗搧姘歌繙娌℃湁
    ``meta.woocommerce_id``锛屼箣鍚庝换浣曚竴娆℃帹閫侀兘浼氭妸瀹冨綋鎴愭柊鍟嗗搧鍐?POST 涓€娆°€?
    鍥炲啓澶辫触涓嶅奖鍝嶆祦姘寸嚎缁撴灉鈥斺€斿晢鍝佺‘瀹炲凡缁忓湪 WooCommerce 涓婃灦浜嗭紝杩欓噷鍙ˉ鏈湴鍏宠仈銆?    """
    from app.models.product import Product
    from app.services.wc_product_link_service import remember_wc_product

    normalized = str(sku or "").strip()
    if not normalized or not wc_id:
        return
    try:
        product = (
            (
                await session.execute(
                    select(Product).where(
                        Product.workspace_id == workspace_id,
                        Product.sku == normalized,
                        Product.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )
        if product is None:
            logger.warning("涓婃灦鎴愬姛浣嗘湰鍦版壘涓嶅埌瀵瑰簲鍟嗗搧锛岃烦杩囧叧鑱斿洖鍐?sku=%s", normalized)
            return
        await remember_wc_product(session, product=product, wc_id=int(wc_id))
        await session.flush()
    except Exception as exc:  # noqa: BLE001
        logger.warning("鍥炲啓 WooCommerce 鍏宠仈澶辫触 sku=%s: %s", normalized, exc)


async def run_pipeline(
    product_info: dict[str, Any],
    *,
    auto_list: bool = False,
    include_images: bool = False,
    session: AsyncSession | None = None,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    杩愯瀹屾暣鐨勪骇鍝佺鍒扮宸ヤ綔娴?
    Args:
        product_info: 鍟嗗搧淇℃伅
        auto_list: 鏄惁鑷姩涓婃灦锛堥粯璁alse锛岄渶瑕佷汉宸ョ‘璁わ級
        include_images: 鏄惁鍖呭惈鍥剧墖鐢熸垚锛堥渶瑕佹暟鎹簱session锛岄粯璁alse锛?        session: 鏁版嵁搴撲細璇濄€備紶鍏ユ椂鎵ц V3.0 閫夊搧闂搁棬锛堣惤搴撳€欓€夊苟璇勪及鍚﹀喅锛夛紝
            涓?None 鏃堕椄闂ㄦ爣璁?skipped銆佷笉璇勪及涔熶笉闃绘柇锛屼繚鎸佹棫璋冪敤鏂硅涓轰笉鍙樸€?        workspace_id: 宸ヤ綔绌洪棿 ID锛岄椄闂ㄨ惤搴撲娇鐢紱缂虹渷鐢ㄩ粯璁ゅ伐浣滅┖闂?        trace_id: 鍏ㄩ摼璺拷韪?ID

    Returns:
        宸ヤ綔娴佺粨鏋?    """
    pipeline_id = str(uuid.uuid4())
    start_time = time.time()
    steps_result: dict[str, Any] = {}
    errors: list[str] = []

    logger.info("Pipeline %s started for product: %s", pipeline_id, product_info.get("name", "unknown"))

    # ===== 1688閾炬帴鍘婚噸妫€鏌ワ紙涓氬姟瑙勫垯锛氬悓涓€閾炬帴鍙兘涓婃灦涓€娆★級 =====
    if session is not None:
        source_url = product_info.get("source_url", "").strip()
        source_offer_id = product_info.get("source_id", "").strip()
        if source_url or source_offer_id:
            from sqlalchemy import select as sa_select
            from app.models.product import Product as ProductModel
            from app.core.workspace import DEFAULT_WORKSPACE_ID
            existing = await session.execute(
                sa_select(ProductModel).where(
                    ProductModel.workspace_id == (workspace_id or DEFAULT_WORKSPACE_ID),
                    (ProductModel.source_url == source_url) if source_url else False,
                    ProductModel.status.notin_(["deleted", "trash"]),
                ).limit(1)
            )
            duplicate = existing.scalar_one_or_none()
            if duplicate:
                raise PipelineError(
                    f"璇?688鍟嗗搧宸插瓨鍦ㄧ郴缁熶腑锛圛D: {duplicate.id}锛孲KU: {duplicate.sku}锛岀姸鎬? {duplicate.status}锛夈€?
                    f"鍚屼竴閾炬帴绂佹閲嶅涓婃灦銆傚闇€閲嶆柊涓婃灦锛岃鍏堝垹闄ゅ師鏈夎褰曘€?
                )
            logger.info("Pipeline %s passed duplicate check: source_url=%s source_offer_id=%s",
                       pipeline_id, source_url, source_offer_id)

    try:
        # Step 1: 鍟嗗搧淇℃伅杈撳叆
        steps_result["input"] = {
            "status": "completed",
            "data": product_info,
            "timestamp": datetime.now().isoformat(),
        }
        logger.info("Pipeline %s Step 1 (input) completed", pipeline_id)

        # Step 2: AI浜у搧鍒嗘瀽
        try:
            analysis_result = await analyze_and_generate_report(product_info)
            if analysis_result["success"]:
                steps_result["analysis"] = {
                    "status": "completed",
                    "data": {
                        "ai_recognition": analysis_result["data"]["ai_recognition"],
                        "product_report": analysis_result["data"]["product_report"],
                    },
                    "timestamp": datetime.now().isoformat(),
                }
                logger.info("Pipeline %s Step 2 (analysis) completed", pipeline_id)
            else:
                raise PipelineError(analysis_result.get("error", "Analysis failed"))
        except Exception as e:
            errors.append(f"Analysis failed: {str(e)}")
            steps_result["analysis"] = {"status": "failed", "error": str(e)}
            logger.error("Pipeline %s Step 2 (analysis) failed: %s", pipeline_id, str(e))

        # 鑾峰彇浜у搧鎶ュ憡锛堝鏋滃垎鏋愭垚鍔燂級
        product_report = steps_result.get("analysis", {}).get("data", {}).get("product_report", {})

        # Step 2.5: 浜у搧鏁版嵁灏辩华闂ㄧ (SOP Step 1.5)
        # Validates weight, dimensions, material, etc. before image generation.
        # Does NOT block 鈥?logs warnings and continues, but marks readiness in result.
        try:
            readiness = check_readiness(product_info, trace_id=trace_id or pipeline_id)
            steps_result["readiness"] = {
                "status": "completed",
                "ready": readiness.ready,
                "score": str(readiness.score),
                "missing_fields": readiness.missing_fields,
                "present_fields": readiness.present_fields,
                "recommendations": readiness.recommendations,
                "report": format_readiness_report(readiness),
                "timestamp": datetime.now().isoformat(),
            }
            if not readiness.ready:
                logger.warning(
                    "Pipeline %s Step 2.5 (readiness) WARNING: score=%.1f missing=%s",
                    pipeline_id, float(readiness.score), readiness.missing_fields,
                )
            else:
                logger.info(
                    "Pipeline %s Step 2.5 (readiness) passed: score=%.1f",
                    pipeline_id, float(readiness.score),
                )
        except Exception as e:
            steps_result["readiness"] = {"status": "skipped", "error": str(e)}
            logger.warning("Pipeline %s Step 2.5 (readiness) skipped: %s", pipeline_id, str(e))

        # Step 3: 涓诲浘鐢熶骇
        try:
            main_image_result = run_main_image_workflow(product_info)
            if main_image_result["success"]:
                main_image_data = main_image_result["data"]
                
                # BUG #5 fix: 鐢熸垚瀹為檯鍥剧墖锛堜娇鐢?Pollinations.ai 鍏嶈垂妯″瀷锛?                if session and main_image_data.get("directions"):
                    try:
                        from app.services.image_generation_service import generate_image_and_save
                        import random
                        
                        generated_images = []
                        directions = main_image_data.get("directions", [])
                        
                        # 涓烘瘡涓柟鍚戠敓鎴愪竴寮犲浘鐗囷紙鏈€澶?3 寮狅級
                        for i, direction in enumerate(directions[:3]):
                            direction_name = direction.get("direction", "")
                            description = direction.get("description", "")
                            
                            # 鏋勫缓鑻辨枃 Prompt锛堝皢涓枃缈昏瘧涓鸿嫳鏂囷紝鐢ㄤ簬 AI 鍥剧墖鐢熸垚锛?                            # 绠€鍗曠炕璇戯細绉婚櫎涓枃锛屼繚鐣欒嫳鏂囧叧閿瘝
                            name_en = product_info.get('name', 'product')
                            # 灏濊瘯鎻愬彇鑻辨枃閮ㄥ垎锛堝鏋滄湁锛?                            import re
                            en_parts = re.findall(r'[a-zA-Z]+', name_en)
                            if en_parts:
                                name_en = ' '.join(en_parts[:10])
                            else:
                                name_en = 'outdoor folding chair'  # 榛樿鑻辨枃鎻忚堪
                            
                            direction_en = direction_name
                            # 缈昏瘧甯歌鏂瑰悜鍚嶇О
                            direction_map = {
                                '鐧藉簳娓呯埥': 'white background clean',
                                '鐪熷疄鍦烘櫙': 'realistic outdoor scene',
                                '淇冮攢杞寲': 'promotional sale',
                                '鐢熸椿鏂瑰紡': 'lifestyle scene',
                                '缁嗚妭灞曠ず': 'product detail closeup'
                            }
                            direction_en = direction_map.get(direction_name, 'product photography')
                            
                            description_en = description
                            # 绠€鍗曠Щ闄や腑鏂囧瓧绗︼紝淇濈暀鑻辨枃
                            description_en = re.sub(r'[\u4e00-\u9fff]+', ' ', description_en)
                            description_en = ' '.join(description_en.split())  # 娓呯悊澶氫綑绌烘牸
                            
                            prompt = f"{name_en}, {direction_en}, {description_en}, premium quality, e-commerce photography, high detail"
                            
                            # 浣跨敤 Pollinations.ai 鍏嶈垂妯″瀷
                            gen_task = await generate_image_and_save(
                                session,
                                prompt=prompt,
                                use_case="main_image",
                                model=None,
                                width=1024,
                                height=1024,
                            )
                            
                            if gen_task and gen_task.image_url:
                                generated_images.append(gen_task.image_url)
                                logger.info("Pipeline %s Step 3: generated image %d/%d: %s", 
                                           pipeline_id, i+1, min(3, len(directions)), gen_task.image_url)
                        
                        if generated_images:
                            main_image_data["generated_images"] = generated_images
                            logger.info("Pipeline %s Step 3: successfully generated %d images", pipeline_id, len(generated_images))
                    except Exception as img_err:
                        logger.warning("Pipeline %s Step 3: image generation failed: %s", pipeline_id, str(img_err))
                
                steps_result["main_image"] = {
                    "status": "completed",
                    "data": main_image_data,
                    "timestamp": datetime.now().isoformat(),
                }
                logger.info("Pipeline %s Step 3 (main_image) completed", pipeline_id)
            else:
                raise PipelineError(main_image_result.get("error", "Main image generation failed"))
        except Exception as e:
            errors.append(f"Main image generation failed: {str(e)}")
            steps_result["main_image"] = {"status": "failed", "error": str(e)}
            logger.error("Pipeline %s Step 3 (main_image) failed: %s", pipeline_id, str(e))

        # Step 4: 鐢熷浘Prompt鐢熸垚
        try:
            if product_report:
                # 鐢熸垚涓诲浘Prompt锛堢櫧搴曟竻鐖芥柟鍚戯級
                main_prompt_result = generate_full_prompt(product_report, page_type="brand_scene")
                # 鐢熸垚璇︽儏椤礟rompt
                detail_prompt_result = generate_full_prompt(product_report, page_type="feature_selling")

                steps_result["prompt"] = {
                    "status": "completed",
                    "data": {
                        "main_image_prompt": main_prompt_result["data"]["full_prompt"] if main_prompt_result["success"] else "",
                        "detail_image_prompt": detail_prompt_result["data"]["full_prompt"] if detail_prompt_result["success"] else "",
                        "prompt_parts": main_prompt_result["data"]["parts"] if main_prompt_result["success"] else {},
                    },
                    "timestamp": datetime.now().isoformat(),
                }
                logger.info("Pipeline %s Step 4 (prompt) completed", pipeline_id)
            else:
                steps_result["prompt"] = {"status": "skipped", "reason": "No product report available"}
        except Exception as e:
            errors.append(f"Prompt generation failed: {str(e)}")
            steps_result["prompt"] = {"status": "failed", "error": str(e)}
            logger.error("Pipeline %s Step 4 (prompt) failed: %s", pipeline_id, str(e))

        # Step 5: 涓婃灦鏁版嵁鐢熸垚锛堝惈鑻辨枃鏈湴鍖栵紝鐩爣甯傚満榛樿 US锛?        try:
            main_image_data = steps_result.get("main_image", {}).get("data", {})
            listing_data = _generate_listing_data(product_info, product_report, main_image_data)
            listing_data = await _english_localize_listing_data(listing_data)
            # 鐢ㄨ嫳鏂囨爣棰樺洖濉富鍥炬柟鍚?prompt 鐨勪富浣?鑳屾櫙锛屼繚璇侀€佺敓鍥炬ā鍨嬪叏鑻辨枃
            try:
                english_name = listing_data.get("name", "")
                if english_name and not _has_cjk(english_name):
                    localized_mi = localize_main_image_prompts(main_image_data, english_name)
                    steps_result["main_image"]["data"] = localized_mi
            except Exception as loc_err:  # noqa: BLE001
                logger.warning("Backfill English main-image prompt failed: %s", loc_err)
            steps_result["listing_data"] = {
                "status": "completed",
                "data": listing_data,
                "timestamp": datetime.now().isoformat(),
            }
            logger.info("Pipeline %s Step 5 (listing_data) completed; localization=%s",
                        pipeline_id, listing_data.get("_localization", {}).get("status", "n/a"))
        except Exception as e:
            errors.append(f"Listing data generation failed: {str(e)}")
            steps_result["listing_data"] = {"status": "failed", "error": str(e)}
            logger.error("Pipeline %s Step 5 (listing_data) failed: %s", pipeline_id, str(e))

        # Step 6: V3.0 閫夊搧闂搁棬锛堝叚缁磋瘎鍒?+ V1-V12 涓€绁ㄥ惁鍐?+ 婕忔枟闃舵锛?        # 闂搁棬蹇呴』鍦ㄤ笂鏋朵箣鍓嶏細琚竴绁ㄥ惁鍐崇殑浜у搧涓嶅厑璁歌繘鍏?WooCommerce锛屽惁鍒?        # 銆屼富鍔ㄦ嫆缁濅笉閫傚悎 Nuotao 鐨勫晢鍝併€嶈繖鏉?V3.0 鏍稿績绛栫暐褰㈠悓铏氳銆?        gate: dict[str, Any] | None = None
        if session is not None:
            try:
                gate_listing_data = steps_result.get("listing_data", {}).get("data", {})
                if not gate_listing_data:
                    raise PipelineError("鏃犱笂鏋舵暟鎹紝鏃犳硶鎵ц V3.0 闂搁棬")
                gate = await run_v3_gate(
                    session,
                    product_info,
                    gate_listing_data,
                    workspace_id=workspace_id,
                    trace_id=trace_id or f"pipeline-{pipeline_id}",
                )
                steps_result["v3_gate"] = {
                    "status": "completed",
                    "data": gate,
                    "timestamp": datetime.now().isoformat(),
                }
                logger.info(
                    "Pipeline %s Step 6 (v3_gate) completed: verdict=%s, nuotao=%s, failed=%s",
                    pipeline_id, gate.get("verdict"), gate.get("nuotao_total"),
                    gate.get("veto_failed"),
                )
            except Exception as e:
                errors.append(f"V3.0 gate failed: {e!s}")
                steps_result["v3_gate"] = {"status": "failed", "error": str(e)}
                logger.error("Pipeline %s Step 6 (v3_gate) failed: %s", pipeline_id, str(e))
        else:
            steps_result["v3_gate"] = {
                "status": "skipped",
                "reason": "鏈彁渚涙暟鎹簱浼氳瘽锛孷3.0 閫夊搧闂搁棬鏈墽琛?,
            }
            logger.warning(
                "Pipeline %s Step 6 (v3_gate) skipped: no DB session supplied", pipeline_id
            )

        # Step 7: 涓婃灦WooCommerce锛堝彲閫夛紝闇€瑕佷汉宸ョ‘璁わ紱琚椄闂ㄥ惁鍐冲垯闃绘柇锛?        # 闂搁棬鍚﹀喅瑕佸湪浜哄伐纭鍓嶅氨鏆撮湶锛氳嫢浠嶆彁绀恒€岃纭涓婃灦銆嶏紝琚惁鍐崇殑浜у搧
        # 浼氳浜哄伐鏀捐锛岄椄闂ㄧ瓑浜庢病瑁呫€?        gate_blocked = bool(gate and gate.get("blocked"))
        gate_needs_review = bool(gate and gate.get("verdict") == GATE_NEEDS_REVIEW)

        if gate_blocked:
            steps_result["listing"] = {
                "status": "blocked",
                "error": f"V3.0 闂搁棬鍚﹀喅锛岀姝笂鏋讹細{(gate or {}).get('reason')}",
                "gate": gate,
                "message": "浜у搧瑙﹀彂涓€绁ㄥ惁鍐筹紝涓嶅厑璁镐笂鏋讹紱濡傞渶涓婃灦椤讳汉宸ュ鏍稿苟鐣欐。",
            }
            logger.warning(
                "Pipeline %s Step 7 (listing) blocked by V3.0 gate: %s",
                pipeline_id, (gate or {}).get("veto_failed"),
            )
        elif gate_needs_review:
            # Needs-review is checked BEFORE auto_list: with auto_list ahead, this
            # branch was unreachable and a flagged product would be pushed to
            # WooCommerce anyway - the gate degraded to a footnote. Review is a
            # business decision and must win over an automation flag.
            steps_result["listing"] = {
                "status": "pending_review",
                "gate": gate,
                "message": f"V3.0 闂搁棬寰呬汉宸ュ鏍革細{(gate or {}).get('reason')}",
            }
        elif auto_list:
            try:
                listing_data = steps_result.get("listing_data", {}).get("data", {})
                if listing_data:
                    # 妫€鏌ユ槸鍚︾鍒剁墿鍝?                    restricted, reason = is_restricted(listing_data.get("name", ""), listing_data.get("sku", ""))
                    if restricted:
                        raise PipelineError(f"Product is restricted: {reason}")

                    listing_result = list_to_woocommerce(listing_data, status="draft")
                    steps_result["listing"] = {
                        "status": "completed" if listing_result.get("success") else "failed",
                        "data": listing_result,
                        "timestamp": datetime.now().isoformat(),
                    }
                    if listing_result.get("success"):
                        logger.info("Pipeline %s Step 7 (listing) completed: WC ID=%s", pipeline_id, listing_result.get("woocommerce_id"))
                        # 涓婃灦鎴愬姛蹇呴』鍥炲啓鏈湴鍏宠仈锛屽惁鍒欐湰鍦拌姘歌繙娌℃湁
                        # meta.woocommerce_id锛屽悗缁换浣曚竴娆℃帹閫侀兘浼氶噸鏂?POST 寤烘柊鍟嗗搧銆?                        if session is not None and listing_result.get("woocommerce_id"):
                            from app.core.workspace import DEFAULT_WORKSPACE_ID

                            await _remember_listed_product(
                                session,
                                workspace_id=workspace_id or DEFAULT_WORKSPACE_ID,
                                sku=listing_data.get("sku"),
                                wc_id=listing_result.get("woocommerce_id"),
                            )
                    else:
                        errors.append(f"Listing failed: {listing_result.get('error')}")
                        logger.error("Pipeline %s Step 7 (listing) failed: %s", pipeline_id, listing_result.get("error"))
            except Exception as e:
                errors.append(f"Listing failed: {str(e)}")
                steps_result["listing"] = {"status": "failed", "error": str(e)}
                logger.error("Pipeline %s Step 7 (listing) failed: %s", pipeline_id, str(e))
        else:
            steps_result["listing"] = {
                "status": "pending_confirmation",
                "gate": gate,
                "message": "涓婃灦鏁版嵁宸茬敓鎴愶紝璇蜂汉宸ョ‘璁ゅ悗鎵ц涓婃灦",
            }

        # 璁＄畻鎬讳綋鐘舵€併€傞椄闂ㄥ惁鍐虫槸鏄庣‘鐨勪笟鍔＄粨璁猴紝涓嶆槸鎶€鏈敊璇細鍗曠嫭缁欏嚭
        # blocked 鐘舵€侊紝璁╄皟鐢ㄦ柟鑳藉尯鍒嗐€岃窇澶辫触浜嗐€嶅拰銆岃閫夊搧绛栫暐鎷掔粷浜嗐€嶃€?        completed_steps = sum(1 for s in steps_result.values() if s.get("status") == "completed")
        total_steps = len(PIPELINE_STEPS)
        gate_verdict = (gate or {}).get("verdict")
        if gate_blocked:
            overall_status = "blocked"
        elif errors:
            overall_status = "partial" if completed_steps > 0 else "failed"
        else:
            overall_status = "completed"

        elapsed_time = time.time() - start_time

        result = {
            "success": overall_status in ["completed", "partial"],
            "data": {
                "pipeline_id": pipeline_id,
                "status": overall_status,
                "completed_steps": completed_steps,
                "total_steps": total_steps,
                "progress": round(completed_steps / total_steps * 100, 1),
                "elapsed_time_seconds": round(elapsed_time, 2),
                "steps": steps_result,
                "errors": errors,
                "product_name": _safe_get(product_info, "name", ""),
                "sku": steps_result.get("listing_data", {}).get("data", {}).get("sku", ""),
                # V3.0 闂搁棬缁撹锛氳皟鐢ㄦ柟鎹鍐冲畾鏄惁鍏佽纭涓婃灦
                "v3_gate": gate,
                "gate_verdict": gate_verdict,
                "gate_blocked": gate_blocked,
                "gate_needs_review": gate_needs_review,
            },
            "error": None if not errors else f"{len(errors)} errors occurred",
        }
        if gate_blocked:
            result["error"] = f"V3.0 閫夊搧闂搁棬鍚﹀喅锛岀姝笂鏋讹細{(gate or {}).get('reason')}"

        logger.info("Pipeline %s finished: status=%s, completed=%d/%d, errors=%d",
                    pipeline_id, overall_status, completed_steps, total_steps, len(errors))

        return result

    except Exception as e:
        logger.error("Pipeline %s unexpected error: %s", pipeline_id, str(e))
        return {
            "success": False,
            "data": {
                "pipeline_id": pipeline_id,
                "status": "failed",
                "steps": steps_result,
                "errors": [str(e)],
            },
            "error": str(e),
        }


# ============ 鑷姩琛ラ綈鍥剧墖 ============

_MAIN_IMG_PROMPTS = [
    "pure white background, professional e-commerce product photography, {product_name}, front view, studio lighting, high detail",
    "pure white background, clean e-commerce hero shot, {product_name}, angled front view, soft shadows, sharp focus",
    "lifestyle outdoor scene, {product_name} in use at a camping site, golden hour lighting, natural setting",
    "detail closeup shot, {product_name}, highlighting premium build quality, macro photography style",
    "lifestyle scene, {product_name} on a picnic table in a forest clearing, warm natural light",
]

_DETAIL_IMG_PROMPTS = [
    "product specification diagram, {product_name}, showing dimensions and features, clean infographic style, white background",
    "folded state showcase, {product_name} compactly folded, portability feature highlight, clean background",
    "assembly instructions, {product_name} being set up step by step, clear and simple visual guide",
    "scale comparison, {product_name} next to common outdoor items for size reference, studio lighting",
    "weather resistance demo, {product_name} in outdoor rain, water-resistant feature showcase",
    "weight demonstration, {product_name} being carried easily by one hand, ultralight feature highlight",
]


async def _auto_generate_missing_images(
    session: "AsyncSession",
    listing_data: dict[str, Any],
    pipeline_result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """褰撳浘鐗囬綈濂楅棬绂佹湭閫氳繃鏃讹紝鑷姩璋冪敤 AI 鐢熷浘琛ラ綈缂哄け鐨勪富鍥惧拰璇︽儏鍥俱€?
    Returns:
        (updated_listing_data, gen_stats)
        gen_stats: {"generated_main": int, "generated_detail": int, "total_generated": int, "errors": list}
    """
    from app.services.image_generation_service import generate_image_and_save

    product_name = listing_data.get("name", "")
    short_desc = listing_data.get("short_description", "") or listing_data.get("description", "")
    selling_points = listing_data.get("selling_points", [])

    gen_stats = {"generated_main": 0, "generated_detail": 0, "total_generated": 0, "errors": []}

    # 鏀堕泦宸叉湁鍥剧墖
    existing_main = _dedupe_real_image_urls(listing_data.get("main_images"))
    existing_detail = _dedupe_real_image_urls(listing_data.get("detail_images"))
    # 涔熺湅鎵佸钩 images 閲屾湁娌℃湁宸茶鍒嗙被鐨?    existing_all = _dedupe_real_image_urls(listing_data.get("images"))

    # ---- 琛ラ綈涓诲浘 (need 5) ----
    needed_main = REQUIRED_MAIN_IMAGES - len(existing_main)
    new_main_urls: list[str] = []
    for i in range(needed_main):
        idx = i % len(_MAIN_IMG_PROMPTS)
        prompt = _MAIN_IMG_PROMPTS[idx].format(product_name=product_name or "outdoor product")
        if short_desc:
            prompt += f", {short_desc[:80]}"
        try:
            task = await generate_image_and_save(
                session,
                workspace_id=None,
                prompt=prompt,
                use_case="main_image",
                width=1024,
                height=1024,
            )
            if task and task.image_url and task.image_url not in existing_main + new_main_urls:
                new_main_urls.append(task.image_url)
                gen_stats["generated_main"] += 1
                logger.info("Auto-generated main image %d/%d: %s", gen_stats["generated_main"], needed_main, task.image_url)
        except Exception as e:
            gen_stats["errors"].append(f"main_image_gen_{i}: {str(e)[:100]}")
            logger.warning("Auto-generate main image failed: %s", str(e))

    # ---- 琛ラ綈璇︽儏鍥?(need 6) ----
    needed_detail = REQUIRED_DETAIL_IMAGES - len(existing_detail)
    new_detail_urls: list[str] = []
    for i in range(needed_detail):
        idx = i % len(_DETAIL_IMG_PROMPTS)
        prompt = _DETAIL_IMG_PROMPTS[idx].format(product_name=product_name or "outdoor product")
        if selling_points and selling_points[0]:
            prompt += f", feature: {selling_points[0][:60]}"
        try:
            task = await generate_image_and_save(
                session,
                workspace_id=None,
                prompt=prompt,
                use_case="detail_image",
                width=768,
                height=1024,
            )
            if task and task.image_url and task.image_url not in existing_detail + new_detail_urls:
                new_detail_urls.append(task.image_url)
                gen_stats["generated_detail"] += 1
                logger.info("Auto-generated detail image %d/%d: %s", gen_stats["generated_detail"], needed_detail, task.image_url)
        except Exception as e:
            gen_stats["errors"].append(f"detail_image_gen_{i}: {str(e)[:100]}")
            logger.warning("Auto-generate detail image failed: %s", str(e))

    gen_stats["total_generated"] = gen_stats["generated_main"] + gen_stats["generated_detail"]

    # 鍚堝苟鍥?listing_data
    all_main = existing_main + new_main_urls
    all_detail = existing_detail + new_detail_urls
    listing_data["main_images"] = [{"src": u} for u in all_main]
    listing_data["detail_images"] = [{"src": u} for u in all_detail]
    # 鏇存柊鎵佸钩 images 淇濇寔鍏煎
    all_flat = all_main + all_detail
    listing_data["images"] = [{"src": u} for u in all_flat]

    logger.info(
        "Auto-image-gen done: main=%d/%d detail=%d/%d total_gen=%d errors=%d",
        len(all_main), REQUIRED_MAIN_IMAGES,
        len(all_detail), REQUIRED_DETAIL_IMAGES,
        gen_stats["total_generated"], len(gen_stats["errors"]),
    )
    return listing_data, gen_stats


async def confirm_and_list(
    pipeline_result: dict[str, Any],
    *,
    status: str = "publish",
    force: bool = False,
    session: "AsyncSession" | None = None,
) -> dict[str, Any]:
    """
    浜哄伐纭鍚庢墽琛屼笂鏋?
    Args:
        pipeline_result: 宸ヤ綔娴佺粨鏋滐紙鍖呭惈listing_data锛?        status: 涓婃灦鐘舵€侊紙publish/draft/pending锛?
    Returns:
        涓婃灦缁撴灉
    """
    try:
        listing_data = pipeline_result.get("data", {}).get("steps", {}).get("listing_data", {}).get("data", {})
        if not listing_data:
            return {"success": False, "error": "No listing data found in pipeline result"}

        # 妫€鏌ユ槸鍚︾鍒剁墿鍝?        restricted, reason = is_restricted(listing_data.get("name", ""), listing_data.get("sku", ""))
        if restricted:
            return {"success": False, "error": f"Product is restricted: {reason}"}

        # 鍥剧墖榻愬闂ㄧ锛堢‖闂ㄧ锛夛細姝ｅ紡鍙戝竷鏃跺己鍒惰姹備富鍥?+璇︽儏6榻愬锛?        # 鑽夌妯″紡鍏佽涓嶅畬鏁存暟鎹紙鐢ㄦ埛鍚庣画鍙ˉ鍥惧啀鍙戝竷锛夈€?        # force=True 鏃惰烦杩囷紙娴嬭瘯/浜哄伐纭鍦烘櫙锛夈€?        # 闂ㄧ鏈€氳繃鏃讹紝鑷姩璋冪敤 AI 鐢熷浘琛ラ綈缂哄け鍥剧墖鍚庡啀閲嶈瘯銆?        gate = check_image_gate(listing_data)
        gate_notice = "锛?.join(gate.get("reasons", []))
        if not gate.get("passed") and not force and status != "draft":
            logger.info(
                "Image gate failed for sku=%s, auto-generating missing images: %s",
                listing_data.get("sku", ""), gate_notice,
            )
            # 浠?pipeline_result 鎻愬彇 product_info 鐢ㄤ簬鐢熷浘 prompt
            product_info = (
                (pipeline_result.get("data") or {}).get("product_info") or {}
            )
            listing_data, gen_stats = await _auto_generate_missing_images(
                session, listing_data, pipeline_result,
            )
            # 閲嶆柊妫€鏌ラ棬绂?            gate2 = check_image_gate(listing_data)
            if not gate2.get("passed"):
                notice2 = "锛?.join(gate2.get("reasons", []))
                logger.warning(
                    "Image gate still failed after auto-generation: %s (gen_stats=%s)",
                    notice2, gen_stats,
                )
                return {
                    "success": False,
                    "error": f"鍥剧墖鐢熸垚鍚庝粛鏈揪鏍囷紝璇锋墜鍔ㄨˉ鍏咃細{notice2}",
                    "image_gate": gate2,
                    "auto_generated": gen_stats,
                }
            logger.info(
                "Image gate passed after auto-generation: main=%d detail=%d gen_stats=%s",
                gate2["main_count"], gate2["detail_count"], gen_stats,
            )

        # Vision 璐ㄩ噺妫€鏌ワ紙SOP Step 6锛夛細闈為樆鏂紝鍙褰曟鏌ョ粨鏋溿€?        # 妫€鏌ヤ骇鍝佸瑙備竴鑷存€с€佹枃瀛楁纭€с€佽儗鏅共鍑€搴︺€佹瀯鍥惧悎鐞嗘€с€?        # 涓嶉樆鏂绾匡紙AGENTS.md 搂1.2 鏈€灏忛棴鐜紭鍏堬級銆?        quality_checks: list[dict[str, Any]] = []
        try:
            images = listing_data.get("images") or listing_data.get("image_urls") or []
            # Get first generated image for quality check (if any)
            generated = images[:1] if images else []
            if generated:
                ref_url = listing_data.get("reference_image") or listing_data.get("source_url")
                result = await check_image_quality(
                    generated_url=generated[0],
                    reference_url=ref_url,
                    image_type="main",
                )
                quality_checks.append({
                    "url": generated[0],
                    "passed": result.passed,
                    "score": result.score,
                    "checked": result.checked,
                    "findings": len(result.findings),
                    "report": format_quality_report(result),
                })
                if not result.checked:
                    logger.warning(
                        "Pipeline Step 6: Vision quality check skipped: %s",
                        result.skipped_reason,
                    )
                elif not result.passed:
                    logger.warning(
                        "Pipeline Step 6: Vision quality check FAILED: score=%.2f findings=%d",
                        result.score, len(result.findings),
                    )
                else:
                    logger.info(
                        "Pipeline Step 6: Vision quality check PASSED: score=%.2f",
                        result.score,
                    )
        except Exception as qc_err:
            logger.warning("Pipeline Step 6: Vision quality check error: %s", str(qc_err))

        listing_result = list_to_woocommerce(listing_data, status=status)
        listing_result["quality_checks"] = quality_checks

        # 鍥剧墖鈫扺C Media Library 鑷姩绠＄嚎锛圥hase 3锛?        # WC API 涓嶄繚璇佽嚜鍔ㄤ笅杞藉閮?URL 鍥剧墖锛岃繖閲屾樉寮忎笂浼犵‘淇?Media Library 鏈夊浘銆?        # 涓嶉樆鏂绾匡紙AGENTS.md 搂1.2锛夛紝鍙褰曠粨鏋溿€?        if listing_result.get("success") and listing_result.get("woocommerce_id"):
            try:
                images = listing_data.get("images") or listing_data.get("image_urls") or []
                if images:
                    wc_id = listing_result["woocommerce_id"]
                    product_name = listing_data.get("name", "")
                    wc_pipeline = await upload_images_to_wc(
                        image_urls=images,
                        wc_product_id=wc_id,
                        product_name=product_name,
                    )
                    listing_result["image_wc_pipeline"] = {
                        "success": wc_pipeline.success,
                        "uploaded": wc_pipeline.uploaded,
                        "failed": wc_pipeline.failed,
                        "verified": wc_pipeline.verified,
                        "report": format_pipeline_report(wc_pipeline),
                    }
                    if wc_pipeline.success:
                        logger.info(
                            "Pipeline: uploaded %d/%d images to WC media for product %d",
                            wc_pipeline.uploaded, wc_pipeline.total, wc_id,
                        )
                    else:
                        logger.warning(
                            "Pipeline: image WC pipeline failed: %d/%d uploaded",
                            wc_pipeline.uploaded, wc_pipeline.total,
                        )
            except Exception as wc_img_err:
                logger.warning("Pipeline: image WC pipeline error: %s", str(wc_img_err))
                listing_result["image_wc_pipeline"] = {
                    "success": False,
                    "error": str(wc_img_err),
                }

        return listing_result

    except Exception as e:
        logger.error("Confirm and list error: %s", str(e))
        return {"success": False, "error": str(e)}


async def upsert_local_listed_product(
    db: "AsyncSession",
    listing_data: dict[str, Any],
    wc_result: dict[str, Any],
    workspace_id: "UUID",
    *,
    source: str = "pipeline",
    source_url: str = "",
) -> dict[str, Any]:
    """
    涓婃灦 WooCommerce 鎴愬姛鍚庯紝鎶婂晢鍝?upsert 鍒版湰鍦?products 涓绘暟鎹〃銆?
    瑙ｅ喅"鍙帹 WC銆佹湰鍦板晢鍝佷富鏁版嵁涓虹┖"鐨勬暟鎹柇灞傦細鎸?workspace + SKU 鏌ユ壘**娲昏**锛?    瀛樺湪鍒欐洿鏂帮紝涓嶅瓨鍦ㄥ垯鏂板缓銆?
    鍒绘剰**涓嶅娲?*杞垹琛岋細``uq_products_workspace_source_offer`` 鏄?    ``WHERE deleted_at IS NULL`` 鐨勯儴鍒嗙储寮曪紝鍥炴敹绔欓噷鐨勮涓嶅崰鐢ㄦ潵婧愰敭浣嶃€傝嫢鎶婃棫琛?    澶嶆椿锛岃€屽悓涓€涓?offer 鏈熼棿宸茬粡閲嶆柊寤烘。锛屽氨浼氱洿鎺ユ挒鍞竴绱㈠紩銆傝繖涔熶笌 WooCommerce
    鍙嶅悜鍚屾銆屽垹鍚庨噸浼犺蛋鏂板缓銆嶇殑鍙ｅ緞涓€鑷淬€?
    Returns:
        {"product_id", "created": bool}
    """
    from app.models.product import Product

    sku = str(listing_data.get("sku") or "").strip()
    name = str(listing_data.get("name") or "").strip()
    if not sku or not name:
        return {"product_id": None, "created": False, "error": "missing sku/name"}

    # WC status 鏄犲皠鍒版湰鍦?commerce status
    wc_status = (wc_result.get("status") or listing_data.get("status") or "draft").lower()
    local_status = "active" if wc_status == "publish" else "draft"

    # tags: listing 閲屽彲鑳芥槸 [{"name":...}] 鎴?["tag",...]
    raw_tags = listing_data.get("tags") or []
    tags: list[str] = []
    for t in raw_tags:
        if isinstance(t, dict):
            if t.get("name"):
                tags.append(str(t["name"]))
        elif t:
            tags.append(str(t))

    # category锛氬彇绗竴涓垎绫?id/鍚?    raw_cats = listing_data.get("categories") or []
    category = None
    if raw_cats:
        first = raw_cats[0]
        category = str(first.get("name") or first.get("id")) if isinstance(first, dict) else str(first)

    # 浠锋牸
    regular_price = listing_data.get("regular_price") or listing_data.get("price")

    row = (
        await db.execute(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.sku == sku,
                Product.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    wc_id = wc_result.get("woocommerce_id")
    base_meta = {
        "woocommerce_id": wc_id,
        "woocommerce_permalink": wc_result.get("permalink"),
        "regular_price": str(regular_price) if regular_price is not None else None,
        "localizations": {"en": {
            "title": name,
            "description": listing_data.get("description", ""),
            "short_description": listing_data.get("short_description", ""),
            "status": "approved",
        }},
    }

    if row is None:
        row = Product(
            workspace_id=workspace_id,
            sku=sku,
            name=name,
            description=(listing_data.get("description") or "")[:2000] or None,
            category=category,
            status=local_status,
            source=source,
            source_url=source_url or None,
            tags=tags,
            target_market="US",
            meta=base_meta,
            deleted_at=None,
        )
        db.add(row)
        await db.flush()
        created = True
    else:
        row.name = name
        if listing_data.get("description"):
            row.description = listing_data["description"][:2000]
        if category:
            row.category = category
        row.status = local_status
        row.tags = tags
        merged_meta = {**(row.meta or {}), **base_meta}
        row.meta = merged_meta
        if source_url:
            row.source_url = source_url
        created = False

    await db.commit()
    await db.refresh(row)
    logger.info(
        "Upserted local product sku=%s wc_id=%s created=%s",
        sku, wc_id, created,
    )
    return {"product_id": str(row.id), "created": created}


# ============================================
# 1688 鍟嗗搧涓€閿鍏?# ============================================


# ---------------------------------------------------------------------------
# 1688 鎶撳彇缁撴灉缂撳瓨锛圔UG-20锛?#
# 鐗涢】 Agent 鍗曟鎶撳彇瀹炴祴 53s/114s/174s/208s锛岃秴杩囧叆鍙ｇ綉鍏筹紙Cloudflare锛夌害 100s
# 鐨勮姹備笂闄愶紝娴忚鍣ㄤ細鏀跺埌 499銆佽繛鎺ヨ鎺愭柇锛屼絾鍚庣浠嶅湪缁х画鎵ц銆備负璁╂搷浣滆€呰兘澶?# 閲嶈瘯鎴愬姛锛岃繖閲屾寜 1688 鍟嗗搧 ID 缂撳瓨鎶撳彇缁撴灉锛氶娆¤皟鐢ㄥ彲鑳借秴鏃讹紝閲嶅瀵煎叆绉掑洖銆?# 骞傜瓑閲嶈瘯璺緞锛岀鍚?AGENTS.md 2.4銆屾墍鏈夊閮ㄨ皟鐢ㄥ繀椤绘湁瓒呮椂銆侀噸璇曪紙骞傜瓑鎺ュ彛锛夈€?# 鐔旀柇涓庨檷绾с€嶃€?# ---------------------------------------------------------------------------
_IMPORT_CACHE_PREFIX = "nuotao:1688-fetch:"
_IMPORT_CACHE_TTL_SECONDS = 3600
_IMPORT_CACHE_TTL_SPARSE = 300  # 绋€鐤忕粨鏋滅煭 TTL锛氳涓嬩竴娆″鍏ラ噸鏂版娊鍙?
_cache_redis: Any = None


def _get_cache_redis() -> Any:
    """鎯版€у崟渚嬶細閬垮厤姣忔璋冪敤閮芥柊寤轰竴鏉?Redis 杩炴帴銆備笉鍙敤鏃惰繑鍥?None锛堢紦瀛橀檷绾т负鍏抽棴锛夈€?""
    global _cache_redis
    if _cache_redis is None:
        try:
            from app.core.redis import create_redis_client

            _cache_redis = create_redis_client()
        except Exception as exc:  # Redis 涓嶅彲鐢ㄤ笉搴旈樆鏂鍏?            logger.warning("1688 import cache: Redis unavailable: %s", exc)
            _cache_redis = False
    return _cache_redis or None


def _import_cache_key(url_or_id: str) -> str:
    pid = parse_1688_url(url_or_id) or str(url_or_id).strip()
    return f"{_IMPORT_CACHE_PREFIX}{pid}"


def _extract_richness(info: dict[str, Any]) -> int:
    """缁撴灉涓板瘜搴︼細灞炴€ф潯鏁?+ 鏄惁甯﹂噸閲?+ 鏄惁甯﹀昂瀵搞€傜敤浜庡湪澶氭鎶藉彇闂存嫨浼樸€?""
    if not isinstance(info, dict):
        return -1
    attrs = info.get("attributes") or []
    score = len(attrs) if isinstance(attrs, list) else 0
    if str(info.get("weight") or "").strip():
        score += 2
    if str(info.get("dimensions") or "").strip():
        score += 2
    return score


def _is_sparse_fetch(result: dict[str, Any]) -> bool:
    """鐗涢】杩斿洖鎴愬姛浣嗘病鏈夊睘鎬ц〃銆侀噸閲忓拰灏哄锛氳涓虹█鐤忥紝鍊煎緱閲嶈瘯涓€娆°€?""
    info = ((result or {}).get("data") or {}).get("product_info") or {}
    return (
        (not (info.get("attributes") or []))
        and not str(info.get("weight") or "").strip()
        and not str(info.get("dimensions") or "").strip()
    )


def _has_minimal_data(result: dict[str, Any]) -> bool:
    """缁撴灉鏄惁宸插叿澶囨渶灏忓彲鐢ㄦ暟鎹細鍚嶇О + 浠锋牸 + 鈮? 寮犲浘鐗囥€?
    绋€鐤忛噸璇曪紙ROUND-4F锛夌殑鐩殑鏄粠灞炴€ц〃涓虹┖鐨勭墰椤跨粨鏋滀腑鑾峰彇鏇村缁村害銆?    浣嗗綋棣栨缁撴灉宸插惈鏍稿績瀛楁锛堝悕绉般€佷环鏍笺€佸浘鐗囷級鏃讹紝閲嶈瘯澶ф鐜囧彧鏄?    鐢?300s 瓒呮椂鎹㈠彇鏃犳敹鐩娾€斺€斿疄娴嬮噸璇?KILL 鐜?> 50%銆傛鏃惰烦杩囬噸璇曪紝
    鐩存帴杩斿洖绋€鐤忕粨鏋滐紝TTL 淇濇寔鐭€间互渚垮悗缁墜鍔ㄦ垨鑷姩閲嶆柊鎶藉彇銆?    """
    info = ((result or {}).get("data") or {}).get("product_info") or {}
    has_name = bool(str(info.get("name") or "").strip())
    has_price = bool(info.get("price"))
    has_image = bool((info.get("images") or []))
    return has_name and has_price and has_image

# 1688 寮€鏀惧钩鍙伴敊璇爜 鈫?鐢ㄦ埛鍙鎻愮ず鐨勭炕璇戣〃銆?# 鍛戒腑閿紙瀛愪覆鍖归厤锛屽ぇ灏忓啓涓嶆晱鎰燂級鍗宠繑鍥?(鐢ㄦ埛鍙涓枃, 绋冲畾鐨?error_code 閿?銆?# 鏈懡涓繑鍥?(None, None) 璁╀笂灞傛部鐢ㄥ師鏂囥€?_1688_ERROR_TRANSLATIONS: list[tuple[str, str, str]] = [
    # (鍖归厤瀛愪覆, 鐢ㄦ埛鍙鎻愮ず, error_code)
    (
        "APIACLDecline",
        "1688 寮€鏀惧钩鍙?AppKey 鏈姞鍏ョ櫧鍚嶅崟锛屾棤娉曟媺鍙栬鍟嗗搧銆傝璁╃鐞嗗憳鍦?1688 寮€鏀惧钩鍙板悗鍙板皢褰撳墠 AppKey 鎺堟潈璁块棶璇ュ晢鍝佹墍灞炲晢瀹?绫荤洰鍚庨噸璇曘€?,
        "APPKEY_ACL_DECLINE",
    ),
    (
        "UserNotLogin",
        "1688 璐︽埛鏈櫥褰曟垨鐧诲綍鎬佸凡杩囨湡锛岃閲嶆柊鎺堟潈鍚庨噸璇曘€?,
        "USER_NOT_LOGIN",
    ),
    (
        "AppKey is not allowed",
        "1688 AppKey 鏃犺闂潈闄愶紙ACL 鎷掔粷锛夈€傝鑱旂郴绠＄悊鍛樺湪 1688 寮€鏀惧钩鍙颁负褰撳墠 AppKey 鎺堟潈瀵瑰簲鍟嗗搧鍟嗗/绫荤洰銆?,
        "APPKEY_ACL_DECLINE",
    ),
    (
        "forbidden",
        "1688 鎷掔粷璁块棶璇ュ晢鍝侊紙鍙兘鏄晢鍝佷笅鏋躲€佸晢瀹跺叧闂€佹垨 AppKey 鏃犳潈闄愶級銆傝妫€鏌ュ晢鍝侀摼鎺ユ槸鍚︽湁鏁堬紝鎴栬仈绯荤鐞嗗憳纭 AppKey 鎺堟潈鑼冨洿銆?,
        "FORBIDDEN",
    ),
    (
        "timeout",
        "1688 鏈嶅姟鍝嶅簲瓒呮椂锛岃绋嶅悗閲嶈瘯銆傝嫢鎸佺画鍑虹幇璇疯仈绯荤鐞嗗憳妫€鏌ヤ笂娓告湇鍔＄姸鎬併€?,
        "UPSTREAM_TIMEOUT",
    ),
    (
        "IllegalParam",
        "1688 杩斿洖鍙傛暟閿欒銆傝妫€鏌ヨ緭鍏ョ殑鍟嗗搧 URL 鏄惁涓哄悎娉曠殑 detail.1688.com/offer/xxx.html 鏍煎紡銆?,
        "ILLEGAL_PARAM",
    ),
]


def _translate_1688_error(error: str | None) -> tuple[str | None, str | None]:
    """鎶?1688 寮€鏀惧钩鍙板師濮嬮敊璇俊鎭炕璇戞垚鐢ㄦ埛鍙鎻愮ず銆?
    杩斿洖 (friendly_message, error_code)銆傛湭鍛戒腑缈昏瘧琛ㄨ繑鍥?(None, None)銆?    鍖归厤閲囩敤瀛愪覆鍖呭惈锛屽ぇ灏忓啓涓嶆晱鎰燂紝閬垮厤涓婃父鎺緸缁嗗井宸紓婕忔帀銆?    """
    if not error:
        return None, None
    lowered = error.lower()
    for needle, friendly, code in _1688_ERROR_TRANSLATIONS:
        if needle.lower() in lowered:
            return friendly, code
    return None, None


async def _cached_fetch_1688_product(url_or_id: str) -> dict[str, Any]:
    """甯?Redis 骞傜瓑缂撳瓨鐨?1688 鍟嗗搧鎶撳彇銆傚懡涓椂闄勫甫 from_cache 鏍囪銆?""
    import json  # 鏈ā鍧楁湭椤跺眰瀵煎叆 json

    key = _import_cache_key(url_or_id)
    redis = _get_cache_redis()
    if redis is not None:
        try:
            raw = await redis.get(key)
            if raw:
                cached = json.loads(raw)
                cached["from_cache"] = True
                logger.info("1688 import cache hit: %s", key)
                return cached
        except Exception as exc:
            logger.warning("1688 import cache read failed for %s: %s", key, exc)

    # ROUND-4F: 鐗涢】鏄?LLM Agent锛屽睘鎬ц〃鎻愬彇涓嶇ǔ瀹氾紙鍚屼竴 offer 瀹炴祴 23 鏉?/ 0 鏉?/ 0 鏉★級銆?    # 绋€鐤忕粨鏋滈噸璇曚竴娆″苟淇濈暀杈冧赴瀵岃€咃紱绋€鐤忕粨鏋滅敤鐭?TTL锛岄伩鍏嶆妸鍗曡杽鏁版嵁缂撳瓨涓€灏忔椂銆?    # ROUND-4G: 鑻ラ娆＄█鐤忕粨鏋滃凡鍚牳蹇冨瓧娈碉紙鍚嶇О+浠锋牸+鍥剧墖锛夛紝璺宠繃閲嶈瘯鈥斺€?    # 瀹炴祴閲嶈瘯 KILL 鐜?> 50%锛屽钩鍧囨氮璐?~297s 浣嗘棤鏁版嵁鏀剁泭銆?    result = await asyncio.to_thread(_fetch_1688_product, url_or_id)
    if _is_sparse_fetch(result) and not _has_minimal_data(result):
        logger.info("1688 fetch sparse (no attributes/weight/dims), no minimal data, retrying once")
        retry = await asyncio.to_thread(_fetch_1688_product, url_or_id)
        first_info = ((result.get("data") or {}).get("product_info") or {})
        retry_info = ((retry.get("data") or {}).get("product_info") or {})
        # 濡傛灉棣栨澶辫触浣嗛噸璇曟垚鍔燂紝鏃犺涓板瘜搴﹀浣曢兘淇濈暀閲嶈瘯缁撴灉
        if (not result.get("success")) and retry.get("success"):
            retry["merged_from_retry"] = True
            result = retry
        elif _extract_richness(retry_info) > _extract_richness(first_info):
            retry["merged_from_retry"] = True
            result = retry
    elif _is_sparse_fetch(result):
        logger.info("1688 fetch sparse but has minimal data (name/price/images), skipping retry")

    ttl = _IMPORT_CACHE_TTL_SECONDS if not _is_sparse_fetch(result) else _IMPORT_CACHE_TTL_SPARSE
    if redis is not None and result.get("success"):
        try:
            await redis.set(
                key,
                json.dumps(result, ensure_ascii=False, default=str),
                ex=ttl,
            )
        except Exception as exc:
            logger.warning("1688 import cache write failed for %s: %s", key, exc)
    return result


def parse_1688_url(url: str) -> str:
    """
    浠?688鍟嗗搧URL涓彁鍙栧晢鍝両D

    鏀寔鐨刄RL鏍煎紡锛?    - https://detail.1688.com/offer/123456789.html
    - https://detail.1688.com/offer/123456789.html?spm=...
    - 123456789锛堢洿鎺ヨ緭鍏ュ晢鍝両D锛?
    Args:
        url: 1688鍟嗗搧URL鎴栧晢鍝両D

    Returns:
        鍟嗗搧ID
    """
    import re

    # 濡傛灉鏄函鏁板瓧锛岀洿鎺ヨ繑鍥?    if url.isdigit():
        return url

    # 浠嶶RL涓彁鍙杘ffer ID
    # 鍖归厤 /offer/鏁板瓧.html 鎴?offerId=鏁板瓧
    patterns = [
        r'/offer/(\d+)\.html',
        r'offerId=(\d+)',
        r'offer/(\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    raise ValueError(f"鏃犳硶浠嶶RL涓彁鍙?688鍟嗗搧ID: {url}")


def convert_1688_to_pipeline_input(
    product_detail: dict[str, Any],
    source_url: str = "",
    source_id: str = "",
) -> dict[str, Any]:
    """
    灏?688鍟嗗搧璇︽儏杞崲涓轰骇鍝佸伐浣滄祦杈撳叆鏍煎紡

    Args:
        product_detail: 1688鍟嗗搧璇︽儏锛堟潵鑷猻ourcing_1688_service.get_product_detail锛?        source_url: 1688鍟嗗搧閾炬帴
        source_id: 1688鍟嗗搧ID

    Returns:
        浜у搧宸ヤ綔娴佽緭鍏ユ牸寮忕殑鍟嗗搧淇℃伅
    """
    product = product_detail.get("product", {}) if product_detail.get("success") else {}

    # 鎻愬彇鍟嗗搧鍚嶇О
    name = product.get("subject", product.get("title", "鏈懡鍚嶅晢鍝?))

    # 鎻愬彇浠锋牸锛堜紭鍏堜繚鐣欏畬鏁翠环鏍煎尯闂达級
    # 浠锋牸锛氬彧淇濈暀绾暟鍊笺€?688 甯歌繑鍥?"楼20" 鎴?"6.7-19.7" 鍖洪棿瀛楃涓诧紝
    # 鐩存帴甯﹀叆 number 杈撳叆妗嗕細閫犳垚瑙ｆ瀽澶辫触锛涘尯闂村彇鏈€楂樹环锛堝お闃宠兘/鍏呯數娆鹃厤缃級銆?    raw_price = str(product.get("price", "")).strip()
    if not raw_price:
        price_info = product.get("price_range") or product.get("priceRange") or []
        if isinstance(price_info, list) and price_info:
            # 鍙栨渶楂樹环鏍硷紙澶槼鑳?鍏呯數娆鹃厤缃級锛岃€屼笉鏄渶浣庝环鏍?            max_price = 0.0
            for p in price_info:
                p_val = p.get("price", 0) if isinstance(p, dict) else p
                try:
                    parsed = float(str(p_val).replace("楼", "").replace(",", ""))
                    if parsed > max_price:
                        max_price = parsed
                except (ValueError, TypeError):
                    pass
            if max_price > 0:
                raw_price = str(max_price)
            else:
                # Fallback to first price
                first_price = price_info[0]
                raw_price = (
                    str(first_price.get("price", ""))
                    if isinstance(first_price, dict)
                    else str(first_price)
                )
    parsed_price = _parse_decimal(raw_price)
    price = str(parsed_price) if parsed_price is not None else ""

    # 鎻愬彇鎻忚堪
    description = product.get("description", "")
    if not description:
        description = product.get("detail", "")

    # 鎻愬彇鏍稿績鍗栫偣锛堜粠鏍囬鍜屽睘鎬т腑鎻愬彇锛?    core_selling_points = []
    attributes = product.get("attributes", [])
    if isinstance(attributes, list):
        for attr in attributes[:5]:
            if isinstance(attr, dict):
                attr_name = attr.get("name") or attr.get("attributeName") or ""
                attr_value = attr.get("value", "")
                if attr_name and attr_value:
                    core_selling_points.append(f"{attr_name}: {attr_value}")

    # 鎻愬彇鏉愯川
    materials = []
    for attr in attributes if isinstance(attributes, list) else []:
        if isinstance(attr, dict):
            attr_name = (
                attr.get("name") or attr.get("attributeName") or ""
            ).lower()
            if "鏉愯川" in attr_name or "material" in attr_name:
                materials.append(attr.get("value", ""))

    # 鎻愬彇灏哄锛圧OUND-4C: 浼樺厛鍖呰灏哄鈥斺€旇繍璐规寜澶栧寘瑁呰璐癸紱
    # 浜у搧瑙勬牸 47x47x90 涓庡寘瑁?92x16x16 宸害 20 鍊嶏級
    dimensions = ""
    pack = {}
    for attr in attributes if isinstance(attributes, list) else []:
        if isinstance(attr, dict):
            attr_name_raw = str(
                attr.get("name") or attr.get("attributeName") or ""
            )
            attr_name = attr_name_raw.lower()
            for axis in ("闀?, "瀹?, "楂?):
                if attr_name.startswith("鍖呰" + axis):
                    pack[axis] = str(attr.get("value", "")).strip()
    if all(pack.get(a) for a in ("闀?, "瀹?, "楂?)):
        dimensions = f"{pack['闀?]}*{pack['瀹?]}*{pack['楂?]}"
    if not dimensions:
        for attr in attributes if isinstance(attributes, list) else []:
            if isinstance(attr, dict):
                attr_name = (
                    attr.get("name") or attr.get("attributeName") or ""
                ).lower()
                if "灏哄" in attr_name or "dimension" in attr_name or "瑙勬牸" in attr_name:
                    dimensions = attr.get("value", "")
                    break

    # 鎻愬彇閲嶉噺锛圧OUND-4C: 鍗曚綅鍦ㄥ睘鎬у悕閲岋紝濡傘€岄噸閲?g)銆嶃€?    # 鍙彇 value 浼氭妸 1800 g 褰撴垚 1800 kg锛岃繍璐归敊涓€鍗冨€嶏紱鏍囧噯缁熶竴 kg锛?    weight = ""
    for attr in attributes if isinstance(attributes, list) else []:
        if isinstance(attr, dict):
            attr_name_raw = str(
                attr.get("name") or attr.get("attributeName") or ""
            )
            attr_name = attr_name_raw.lower()
            if "閲嶉噺" in attr_name or "weight" in attr_name:
                unit_match = re.search(r"[(锛圿([^)锛塢{1,6})[)锛塢", attr_name_raw)
                unit_hint = unit_match.group(1).strip() if unit_match else ""
                raw_value = str(attr.get("value", ""))
                # ROUND-4D: 鍊兼湰韬凡甯﹀崟浣嶆椂涓嶈閲嶅杩藉姞
                if unit_hint and not re.search(
                    r"\d\s*" + re.escape(unit_hint), raw_value, re.I
                ):
                    weight = f"{raw_value} {unit_hint}".strip()
                else:
                    weight = raw_value
                break

    # 鎻愬彇鍟嗗搧鍥剧墖
    images = product.get("images", [])
    if not images:
        images = product.get("imageUrls", [])
    if isinstance(images, list):
        image_urls = [
            (
                img.get("url")
                or img.get("imageUrl")
                or img.get("urls")
                or ""
            )
            if isinstance(img, dict)
            else str(img)
            for img in images
            if img
        ]
    else:
        image_urls = []

    # 鎻愬彇绫荤洰
    category = (
        product.get("category_name")
        or product.get("categoryName")
        or product.get("category")
        or ""
    )

    # 鎻愬彇SKU淇℃伅
    sku_info = product.get("sku_list") or product.get("skuInfos") or []
    if isinstance(sku_info, list) and sku_info:
        first_sku = sku_info[0] if isinstance(sku_info[0], dict) else {}
        sku = first_sku.get("skuCode", first_sku.get("skuId", ""))
    else:
        sku = ""

    # 濡傛灉娌℃湁SKU锛岀敓鎴愪竴涓?    if not sku:
        sku = _generate_sku(name)

    return {
        "name": name,
        "category": str(category),
        "price": price,
        "description": str(description),
        "core_selling_points": core_selling_points[:5],
        "target_audience": "",
        "usage_scenarios": [],
        "product_features": core_selling_points[:5],
        "materials": materials,
        "dimensions": str(dimensions),
        "weight": str(weight),
        "source_url": source_url,
        "source_id": source_id,
        "sku": sku,
        "images": image_urls[:10],  # 鏈€澶?0寮犲浘鐗?        "attributes": attributes,  # ROUND-4A: 淇濈暀鍘熷灞炴€ц〃渚?listing_gate 娑堣垂
        "supplier": product.get("supplier") or {
            "company_name": product.get("company_name", ""),
            "login_id": product.get("supplier_login_id", ""),
        },
    }


def _fetch_1688_product(url_or_id: str) -> dict[str, Any]:
    """1688 鍟嗗搧鎶撳彇涓庢牸寮忚浆鎹紙Step 1-3锛夛紝鍚屾闃诲瀹炵幇銆?
    寮€鏀惧钩鍙颁笌鐗涢】 Agent 閮芥槸鍚屾 HTTP 璋冪敤锛孮A 瀹炴祴鍗曟鍙揪 42s锛屽洜姝ゆ暣娈?    蹇呴』鏀惧埌绾跨▼姹犳墽琛岋紝涓嶈兘鐩存帴鍦ㄤ簨浠跺惊鐜噷璋冪敤锛屽惁鍒欎細鎷栧灝鎵€鏈夊苟鍙戣姹傘€?    """
    import_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        # Step 1: 瑙ｆ瀽URL鎻愬彇鍟嗗搧ID
        product_id = parse_1688_url(url_or_id)
        logger.info("1688 import %s: parsed product_id=%s", import_id, product_id)

        # Step 2: 浼樺厛浣跨敤鐗涢】 Agent 璇诲彇鍟嗗搧锛?688 瀹樻柟 API 鏉冮檺涓嶈冻锛?        from app.services.newton_agent_service import (
            extract_1688_product,
            is_configured as newton_is_configured,
        )

        data_source = "unknown"
        product_detail = None

        if newton_is_configured():
            logger.info(
                "1688 import %s: using Newton Agent to fetch product",
                import_id,
            )
            product_detail = extract_1688_product(url_or_id, product_id)
            data_source = product_detail.get("source", "newton_agent")

        # 鐗涢】 Agent 澶辫触鏃讹紝闄嶇骇鍒?1688 瀹樻柟 API
        if not product_detail or not product_detail.get("success"):
            logger.info(
                "1688 import %s: Newton Agent failed, fallback to open API",
                import_id,
            )
            from app.services.sourcing_1688_service import get_product_detail
            product_detail = get_product_detail(product_id)
            data_source = product_detail.get("source", "1688_open_api")
            if product_detail.get("error"):
                logger.warning(
                    "1688 import %s: open API error: %s",
                    import_id,
                    product_detail.get("error"),
                )

        open_api_error = product_detail.get("error")

        if (
            not product_detail.get("success")
            or product_detail.get("source") == "mock"
        ):
            # 鎶?1688 寮€鏀惧钩鍙扮殑鍘熷閿欒鐮佺炕璇戞垚鐢ㄦ埛鍙銆佸彲鑷姪淇鐨勪腑鏂囨彁绀恒€?            # 甯歌閿欒鐮侊細
            #   gw.APIACLDecline: AppKey is not allowed(acl)  -> AppKey 鏈櫧鍚嶅崟
            #   gw.UserNotLogin / 401 / 403                     -> 鏈巿鏉?/ 鏃犳潈闄?            #   gw.Timeout / connect timeout / read timeout      -> 1688 鏈嶅姟瓒呮椂
            #   gw.IllegalParam / param error                   -> 鍙傛暟閿欒
            error_msg = (
                product_detail.get("error")
                or "鏈幏寰楃湡瀹?1688 鍟嗗搧鏁版嵁锛屽凡鎷掔粷浣跨敤绀轰緥鏁版嵁"
            )
            friendly, error_code = _translate_1688_error(error_msg)
            if friendly:
                error_msg = friendly
            if open_api_error and open_api_error != error_msg:
                error_msg = f"{error_msg}锛堝紑鏀惧钩鍙板師濮嬭繑鍥烇細{open_api_error}锛?
            logger.error(
                "1688 import %s: get product detail failed (code=%s): %s",
                import_id,
                error_code or "unknown",
                error_msg,
            )
            return {
                "success": False,
                "error": error_msg,
                "error_code": error_code,
                "data": {
                    "import_id": import_id,
                    "product_id": product_id,
                    "source_url": url_or_id,
                    "data_source": data_source,
                },
            }

        # Step 3: 杞崲涓轰骇鍝佸伐浣滄祦杈撳叆鏍煎紡
        product_info = convert_1688_to_pipeline_input(
            product_detail,
            source_url=url_or_id,
            source_id=product_id,
        )

        logger.info("1688 import %s: converted product info: name=%s, sku=%s, images=%d",
                    import_id, product_info.get("name"), product_info.get("sku"),
                    len(product_info.get("images", [])))

        return {
            "success": True,
            "data": {
                "import_id": import_id,
                "product_id": product_id,
                "source_url": url_or_id,
                "data_source": data_source or "unknown",
                "product_info": product_info,
                "elapsed_time_seconds": round(time.time() - start_time, 2),
            },
            "error": None,
        }

    except ValueError as e:
        logger.error("1688 import %s: URL parse error: %s", import_id, str(e))
        return {
            "success": False,
            "error": f"URL瑙ｆ瀽澶辫触: {str(e)}",
            "data": {"import_id": import_id, "source_url": url_or_id},
        }
    except Exception as e:
        logger.error("1688 import %s: unexpected error: %s", import_id, str(e))
        return {
            "success": False,
            "error": str(e),
            "data": {"import_id": import_id, "source_url": url_or_id},
        }


async def import_from_1688(
    url_or_id: str,
    *,
    auto_run_pipeline: bool = False,
    auto_list: bool = False,
    session: AsyncSession | None = None,
    workspace_id: UUID | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    浠?688鍟嗗搧URL鎴朓D涓€閿鍏ュ晢鍝佷俊鎭?
    娴佺▼锛?    1. 瑙ｆ瀽URL鎻愬彇鍟嗗搧ID
    2. 浼樺厛璋冪敤1688寮€鏀惧钩鍙帮紝鏈巿鏉冩垨鏃犻摵璐у叧绯绘椂闄嶇骇鍒扮墰椤?Agent
    3. 杞崲涓轰骇鍝佸伐浣滄祦杈撳叆鏍煎紡
    4. 鍙€夛細鑷姩杩愯宸ヤ綔娴侊紙鍚?V3.0 閫夊搧闂搁棬锛?    5. 鍙€夛細鑷姩涓婃灦WooCommerce

    Args:
        url_or_id: 1688鍟嗗搧URL鎴栧晢鍝両D
        auto_run_pipeline: 鏄惁鑷姩杩愯瀹屾暣宸ヤ綔娴?        auto_list: 鏄惁鑷姩涓婃灦锛堜粎鍦╝uto_run_pipeline=True鏃剁敓鏁堬級
        session: 鏁版嵁搴撲細璇濄€備紶鍏ユ椂宸ヤ綔娴佹墽琛?V3.0 閫夊搧闂搁棬锛涗负 None 鏃堕椄闂ㄨ烦杩?        workspace_id: 宸ヤ綔绌洪棿 ID锛岄椄闂ㄨ惤搴撲娇鐢?        trace_id: 鍏ㄩ摼璺拷韪?ID

    Returns:
        瀵煎叆缁撴灉锛屽寘鍚晢鍝佷俊鎭拰鍙€夌殑宸ヤ綔娴佺粨鏋?    """
    logger.info("1688 import started: url=%s, auto_run=%s, auto_list=%s",
                url_or_id, auto_run_pipeline, auto_list)

    # Step 1-3锛氶樆濉炴姄鍙栨斁绾跨▼姹狅紝閬垮厤鍗℃浜嬩欢寰幆
    # ROUND-4E: 鐗涢】鎶撳彇鍙兘瓒呰繃鍏ュ彛缃戝叧瓒呮椂瀵艰嚧瀹㈡埛绔?499锛岀紦瀛樹緵骞傜瓑閲嶈瘯
    result = await _cached_fetch_1688_product(url_or_id)
    if not result.get("success") or not auto_run_pipeline:
        return result

    # Step 4: 鑷姩杩愯瀹屾暣宸ヤ綔娴?    product_info = result["data"]["product_info"]
    logger.info("1688 import: auto running pipeline for %s", url_or_id)
    try:
        # run_pipeline 鏄崗绋嬶細蹇呴』 await锛屽惁鍒?pipeline_result 浼氭槸鍗忕▼瀵硅薄锛?        # 闅忓悗 .get() 鐩存帴 AttributeError锛屾暣鏉¤嚜鍔ㄦ祦杞潤榛樺け鏁堛€?        pipeline_result = await run_pipeline(
            product_info=product_info,
            auto_list=auto_list,
            include_images=False,  # 鍥剧墖鐢熸垚闇€瑕侀澶栨椂闂达紝榛樿涓嶈嚜鍔ㄧ敓鎴?            session=session,
            workspace_id=workspace_id,
            trace_id=trace_id,
        )
    except Exception as e:  # 瀵煎叆鎴愬姛浣嗘祦杞け璐ワ細闄嶇骇杩斿洖瀵煎叆缁撴灉锛屼笉鍚炲紓甯?        logger.error("1688 import: pipeline failed for %s: %s", url_or_id, str(e))
        result["data"]["pipeline_error"] = str(e)
        return result

    result["data"]["pipeline_result"] = pipeline_result
    result["data"]["pipeline_status"] = pipeline_result.get("data", {}).get("status", "unknown")

    logger.info("1688 import completed: success=True, pipeline_status=%s",
                result["data"]["pipeline_status"])
    return result


async def import_and_analyze_from_1688(
    url_or_id: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> dict[str, Any]:
    """
    瀵煎叆鍗曚釜 1688 鍟嗗搧骞剁珛鍗虫墽琛?AI 鍒嗘瀽涓庝骇鍝佹姤鍛娿€?
    璇ュ嚱鏁扮敤浜庣鐞嗙鎵归噺瀵煎叆鐨勯€愭潯宸ヤ綔鍗曞厓銆傞樆濉炵殑 1688 鎶撳彇宸茬敱
    ``import_from_1688`` 鍐呴儴鍒囨崲鍒扮嚎绋嬫墽琛岋紝杩欓噷鐩存帴 await 鍗冲彲锛屼笉浼氶樆濉?    FastAPI 浜嬩欢寰幆銆?    """
    # import_from_1688 宸叉槸鍗忕▼锛堝唴閮ㄨ嚜琛屾妸闃诲鎶撳彇鏀惧埌绾跨▼姹狅級锛岃繖閲岀洿鎺?    # await锛涘啀鐢?to_thread 鍖呰鍙細鎷垮埌鏈墽琛岀殑鍗忕▼瀵硅薄锛岄殢鍚?.get() 宕╂簝銆?    import_result = await import_from_1688(
        url_or_id,
        auto_run_pipeline=False,
        auto_list=False,
    )
    if not import_result.get("success"):
        return import_result

    product_info = import_result.get("data", {}).get("product_info", {})
    supplier = product_info.get("supplier")
    if isinstance(supplier, dict) and not product_info.get("supplier_name"):
        product_info["supplier_name"] = (
            supplier.get("company_name")
            or supplier.get("name")
            or supplier.get("member_id")
            or ""
        )

    try:
        analysis_result = await analyze_and_generate_report(
            product_info,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.error("1688 import analysis failed for %s: %s", url_or_id, str(e))
        return {
            "success": False,
            "error": f"鍟嗗搧宸插鍏ワ紝浣?AI 鍒嗘瀽澶辫触: {e!s}",
            "data": {
                **import_result.get("data", {}),
                "product_info": product_info,
            },
        }

    return {
        "success": True,
        "data": {
            **import_result.get("data", {}),
            "product_info": product_info,
            "ai_recognition": analysis_result["data"]["ai_recognition"],
            "product_report": analysis_result["data"]["product_report"],
            "analysis_metadata": analysis_result["data"].get("metadata", {}),
        },
        "error": None,
    }

