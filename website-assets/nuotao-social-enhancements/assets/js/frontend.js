/**
 * Nuotao Social Enhancements - Frontend JavaScript
 * Version: 1.0.0
 */

(function () {
    'use strict';

    /**
     * 复制链接到剪贴板
     */
    window.nuotaoSocialCopyLink = function (button) {
        var url = button.getAttribute('data-url') || window.location.href;
        var message = window.nuotaoSocialData ? window.nuotaoSocialData.copyText : 'Link copied!';
        var errorMessage = window.nuotaoSocialData ? window.nuotaoSocialData.copyError : 'Failed to copy link';

        // 尝试使用现代 Clipboard API
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url).then(function () {
                nuotaoShowCopyFeedback(button, message, false);
            }).catch(function () {
                nuotaoFallbackCopy(url, button, message, errorMessage);
            });
        } else {
            nuotaoFallbackCopy(url, button, message, errorMessage);
        }
    };

    /**
     * 备用复制方法
     */
    function nuotaoFallbackCopy(url, button, message, errorMessage) {
        var textarea = document.createElement('textarea');
        textarea.value = url;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();

        try {
            document.execCommand('copy');
            nuotaoShowCopyFeedback(button, message, false);
        } catch (err) {
            nuotaoShowCopyFeedback(button, errorMessage, true);
        }

        document.body.removeChild(textarea);
    }

    /**
     * 显示复制反馈
     */
    function nuotaoShowCopyFeedback(button, message, isError) {
        // 创建提示元素
        var tooltip = document.createElement('span');
        tooltip.className = 'nuotao-copy-tooltip' + (isError ? ' error' : '');
        tooltip.textContent = message;
        tooltip.style.cssText = 'position:absolute;background:' + (isError ? '#e74c3c' : '#27ae60') + ';color:#fff;padding:4px 8px;border-radius:4px;font-size:12px;white-space:nowrap;z-index:10000;pointer-events:none;transition:opacity 0.3s;';

        // 定位
        var rect = button.getBoundingClientRect();
        tooltip.style.top = (rect.top - 30 + window.scrollY) + 'px';
        tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2 + window.scrollX) + 'px';

        document.body.appendChild(tooltip);

        // 动画
        setTimeout(function () {
            tooltip.style.opacity = '0';
            setTimeout(function () {
                if (tooltip.parentNode) {
                    tooltip.parentNode.removeChild(tooltip);
                }
            }, 300);
        }, 2000);
    }

    /**
     * 分享窗口打开
     */
    function nuotaoOpenShareWindow(url, width, height) {
        var left = (window.screen.width - width) / 2;
        var top = (window.screen.height - height) / 2;
        var features = 'width=' + width + ',height=' + height + ',left=' + left + ',top=' + top + ',resizable=yes,scrollbars=yes';
        window.open(url, '_blank', features);
    }

    /**
     * 初始化分享按钮点击事件
     */
    function initShareButtons() {
        var shareButtons = document.querySelectorAll('.nuotao-share-btn:not(.nuotao-share-copy)');

        shareButtons.forEach(function (button) {
            button.addEventListener('click', function (e) {
                var href = button.getAttribute('href');
                if (href && href !== '#') {
                    e.preventDefault();
                    nuotaoOpenShareWindow(href, 600, 500);
                }
            });
        });
    }

    /**
     * WooCommerce AJAX 加购事件追踪
     * 修复：WooCommerce 默认使用 AJAX 异步加购，页面不刷新，
     * 服务端 wp_footer 方式无法触发，需在前端监听 added_to_cart 事件
     */
    function initWooCommerceTracking() {
        // 监听 WooCommerce added_to_cart 事件（AJAX 加购成功后触发）
        $(document).on('added_to_cart', function (event, fragments, cart_hash, $button) {
            try {
                // 从按钮 data 属性获取产品信息
                var productId = $button.data('product_id') || $button.attr('data-product_id');
                var productSku = $button.data('product_sku') || '';
                var productName = $button.data('product_name') || '';
                var price = $button.data('price') || 0;
                var quantity = $button.data('quantity') || 1;

                // 如果没有从按钮获取到信息，尝试从 data 属性解析
                if (!productName && $button.length) {
                    var productData = $button.data('product');
                    if (productData && typeof productData === 'object') {
                        productId = productData.id || productId;
                        productName = productData.name || productName;
                        price = productData.price || price;
                        productSku = productData.sku || productSku;
                    }
                }

                var itemId = productSku || productId || 'unknown';
                var value = parseFloat(price) * parseInt(quantity, 10);

                // GA4 add_to_cart 事件
                if (typeof gtag === 'function') {
                    gtag('event', 'add_to_cart', {
                        items: [{
                            id: String(itemId),
                            name: String(productName || 'Product'),
                            price: parseFloat(price) || 0,
                            quantity: parseInt(quantity, 10) || 1
                        }],
                        value: value || 0,
                        currency: window.nuotaoSocialData ? window.nuotaoSocialData.currency : 'USD'
                    });
                }

                // Facebook Pixel AddToCart 事件
                if (typeof fbq === 'function') {
                    fbq('track', 'AddToCart', {
                        content_name: String(productName || 'Product'),
                        content_ids: [String(itemId)],
                        content_type: 'product',
                        value: value || 0,
                        currency: window.nuotaoSocialData ? window.nuotaoSocialData.currency : 'USD'
                    });
                }

                // TikTok Pixel AddToCart 事件
                if (typeof ttq !== 'undefined' && ttq && typeof ttq.track === 'function') {
                    ttq.track('AddToCart', {
                        content_id: String(itemId),
                        content_name: String(productName || 'Product'),
                        value: value || 0,
                        currency: window.nuotaoSocialData ? window.nuotaoSocialData.currency : 'USD'
                    });
                }

                console.log('[Nuotao Social] add_to_cart event tracked:', {
                    id: itemId,
                    name: productName,
                    price: price,
                    quantity: quantity,
                    value: value
                });
            } catch (err) {
                console.error('[Nuotao Social] add_to_cart tracking error:', err);
            }
        });
    }

    /**
     * 页面加载完成后初始化
     */
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            initShareButtons();
            initWooCommerceTracking();
        });
    } else {
        initShareButtons();
        initWooCommerceTracking();
    }

    // 暴露到全局
    window.nuotaoSocial = {
        copyLink: window.nuotaoSocialCopyLink,
        openShareWindow: nuotaoOpenShareWindow
    };

})();
