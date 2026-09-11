<?php
/**
 * 追踪代码类
 *
 * @package Nuotao_Social_Enhancements
 */

if (!defined('ABSPATH')) {
    exit;
}

/**
 * 追踪代码类
 */
class Nuotao_Social_Tracking {

    /**
     * 构造函数
     */
    public function __construct() {
        // Facebook Pixel
        add_action('wp_head', array($this, 'inject_facebook_pixel'), 1);

        // TikTok Pixel
        add_action('wp_head', array($this, 'inject_tiktok_pixel'), 2);

        // GA4
        add_action('wp_head', array($this, 'inject_ga4'), 3);

        // WooCommerce 事件追踪
        add_action('woocommerce_after_single_product', array($this, 'track_product_view'));
        add_action('woocommerce_add_to_cart', array($this, 'track_add_to_cart'), 10, 6);
        add_action('woocommerce_thankyou', array($this, 'track_purchase'));
    }

    /**
     * 检查是否应该注入追踪代码
     */
    private function should_inject() {
        if (Nuotao_Social_Enhancements::is_excluded_user()) {
            return false;
        }
        return true;
    }

    /**
     * 注入 Facebook Pixel
     */
    public function inject_facebook_pixel() {
        if (!$this->should_inject()) {
            return;
        }

        $settings = Nuotao_Social_Enhancements::get_settings();
        $pixel_id = $settings['fb_pixel_id'];

        if (empty($pixel_id)) {
            return;
        }

        $pixel_id = esc_js($pixel_id);
        ?>
        <!-- Facebook Pixel Code (Nuotao Social Enhancements) -->
        <script>
        !function(f,b,e,v,n,t,s)
        {if(f.fbq)return;n=f.fbq=function(){n.callMethod?
        n.callMethod.apply(n,arguments):n.queue.push(arguments)};
        if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
        n.queue=[];t=b.createElement(e);t.async=!0;
        t.src=v;s=b.getElementsByTagName(e)[0];
        s.parentNode.insertBefore(t,s)}(window, document,'script',
        'https://connect.facebook.net/en_US/fbevents.js');
        fbq('init', '<?php echo $pixel_id; ?>');
        fbq('track', 'PageView');
        </script>
        <noscript><img height="1" width="1" style="display:none"
        src="https://www.facebook.com/tr?id=<?php echo $pixel_id; ?>&ev=PageView&noscript=1"
        /></noscript>
        <!-- End Facebook Pixel Code -->
        <?php
    }

    /**
     * 注入 TikTok Pixel
     */
    public function inject_tiktok_pixel() {
        if (!$this->should_inject()) {
            return;
        }

        $settings = Nuotao_Social_Enhancements::get_settings();
        $pixel_id = $settings['tiktok_pixel_id'];

        if (empty($pixel_id)) {
            return;
        }

        $pixel_id = esc_js($pixel_id);
        ?>
        <!-- TikTok Pixel Code (Nuotao Social Enhancements) -->
        <script>
        !function (w, d, t) {
          w.TiktokAnalyticsObject=t;var ttq=w[t]=w[t]||[];ttq.methods=["page","track","identify","instances","debug","on","off","once","ready","alias","group","enableCookie","disableCookie"],ttq.setAndDefer=function(t,e){t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}};for(var i=0;i<ttq.methods.length;i++)ttq.setAndDefer(ttq,ttq.methods[i]);ttq.instance=function(t){for(var e=ttq._i[t]||[],n=0;n<ttq.methods.length;n++)ttq.setAndDefer(e,ttq.methods[n]);return e},ttq.load=function(e,n){var i="https://analytics.tiktok.com/i18n/pixel/events.js";ttq._i=ttq._i||{},ttq._i[e]=[],ttq._i[e]._u=i,ttq._t=ttq._t||{},ttq._t[e]=+new Date,ttq._o=ttq._o||{},n=n||{};var o=document.createElement("script");o.type="text/javascript",o.async=!0,o.src=i+"?sdkid="+e+"&lib="+t;var a=document.getElementsByTagName("script")[0];a.parentNode.insertBefore(o,a)};
          ttq.load('<?php echo $pixel_id; ?>');
          ttq.page();
        }(window, document, 'ttq');
        </script>
        <!-- End TikTok Pixel Code -->
        <?php
    }

    /**
     * 注入 GA4
     */
    public function inject_ga4() {
        if (!$this->should_inject()) {
            return;
        }

        $settings = Nuotao_Social_Enhancements::get_settings();
        $measurement_id = $settings['ga4_measurement_id'];

        if (empty($measurement_id)) {
            return;
        }

        $measurement_id = esc_js($measurement_id);
        ?>
        <!-- Google Analytics 4 (Nuotao Social Enhancements) -->
        <script async src="https://www.googletagmanager.com/gtag/js?id=<?php echo $measurement_id; ?>"></script>
        <script>
          window.dataLayer = window.dataLayer || [];
          function gtag(){dataLayer.push(arguments);}
          gtag('js', new Date());
          gtag('config', '<?php echo $measurement_id; ?>', {
            'anonymize_ip': true
          });
        </script>
        <!-- End Google Analytics 4 -->
        <?php
    }

    /**
     * 追踪商品浏览
     */
    public function track_product_view() {
        if (!$this->should_inject()) {
            return;
        }

        global $product;
        if (!$product) {
            return;
        }

        $settings = Nuotao_Social_Enhancements::get_settings();
        $items = array(array(
            'id' => $product->get_sku() ?: $product->get_id(),
            'name' => $product->get_name(),
            'price' => $product->get_price(),
            'quantity' => 1,
        ));

        // Facebook Pixel
        if (!empty($settings['fb_pixel_id'])) {
            ?>
            <script>
            fbq('track', 'ViewContent', {
                content_name: <?php echo wp_json_encode($product->get_name()); ?>,
                content_ids: ['<?php echo esc_js($product->get_sku() ?: $product->get_id()); ?>'],
                content_type: 'product',
                value: <?php echo esc_js($product->get_price()); ?>,
                currency: '<?php echo esc_js(get_woocommerce_currency()); ?>'
            });
            </script>
            <?php
        }

        // TikTok Pixel
        if (!empty($settings['tiktok_pixel_id'])) {
            ?>
            <script>
            ttq.track('ViewContent', {
                content_id: '<?php echo esc_js($product->get_sku() ?: $product->get_id()); ?>',
                content_name: <?php echo wp_json_encode($product->get_name()); ?>,
                value: <?php echo esc_js($product->get_price()); ?>,
                currency: '<?php echo esc_js(get_woocommerce_currency()); ?>'
            });
            </script>
            <?php
        }

        // GA4
        if (!empty($settings['ga4_measurement_id'])) {
            ?>
            <script>
            gtag('event', 'view_item', {
                items: <?php echo wp_json_encode($items); ?>,
                value: <?php echo esc_js($product->get_price()); ?>,
                currency: '<?php echo esc_js(get_woocommerce_currency()); ?>'
            });
            </script>
            <?php
        }
    }

    /**
     * 追踪加入购物车
     */
    public function track_add_to_cart($cart_item_key, $product_id, $quantity, $variation_id, $variation, $cart_item_data) {
        if (!$this->should_inject()) {
            return;
        }

        $product = wc_get_product($product_id);
        if (!$product) {
            return;
        }

        $settings = Nuotao_Social_Enhancements::get_settings();

        // 存储到 session 以便在页面加载时触发
        if (!session_id()) {
            session_start();
        }
        $_SESSION['nuotao_track_add_to_cart'] = array(
            'id' => $product->get_sku() ?: $product->get_id(),
            'name' => $product->get_name(),
            'price' => $product->get_price(),
            'quantity' => $quantity,
        );

        // 直接输出 JS（通过 AJAX 或页面刷新）
        add_action('wp_footer', array($this, 'output_add_to_cart_tracking'));
    }

    /**
     * 输出加入购物车追踪
     */
    public function output_add_to_cart_tracking() {
        if (!session_id()) {
            session_start();
        }

        if (empty($_SESSION['nuotao_track_add_to_cart'])) {
            return;
        }

        $data = $_SESSION['nuotao_track_add_to_cart'];
        unset($_SESSION['nuotao_track_add_to_cart']);

        $settings = Nuotao_Social_Enhancements::get_settings();
        $currency = get_woocommerce_currency();

        if (!empty($settings['fb_pixel_id'])) {
            ?>
            <script>
            fbq('track', 'AddToCart', {
                content_name: <?php echo wp_json_encode($data['name']); ?>,
                content_ids: ['<?php echo esc_js($data['id']); ?>'],
                content_type: 'product',
                value: <?php echo esc_js($data['price'] * $data['quantity']); ?>,
                currency: '<?php echo esc_js($currency); ?>'
            });
            </script>
            <?php
        }

        if (!empty($settings['tiktok_pixel_id'])) {
            ?>
            <script>
            ttq.track('AddToCart', {
                content_id: '<?php echo esc_js($data['id']); ?>',
                content_name: <?php echo wp_json_encode($data['name']); ?>,
                value: <?php echo esc_js($data['price'] * $data['quantity']); ?>,
                currency: '<?php echo esc_js($currency); ?>'
            });
            </script>
            <?php
        }

        if (!empty($settings['ga4_measurement_id'])) {
            ?>
            <script>
            gtag('event', 'add_to_cart', {
                items: [{
                    id: '<?php echo esc_js($data['id']); ?>',
                    name: <?php echo wp_json_encode($data['name']); ?>,
                    price: <?php echo esc_js($data['price']); ?>,
                    quantity: <?php echo esc_js($data['quantity']); ?>
                }],
                value: <?php echo esc_js($data['price'] * $data['quantity']); ?>,
                currency: '<?php echo esc_js($currency); ?>'
            });
            </script>
            <?php
        }
    }

    /**
     * 追踪购买
     */
    public function track_purchase($order_id) {
        if (!$this->should_inject()) {
            return;
        }

        $order = wc_get_order($order_id);
        if (!$order) {
            return;
        }

        $settings = Nuotao_Social_Enhancements::get_settings();
        $items = array();
        $total = $order->get_total();
        $currency = $order->get_currency();

        foreach ($order->get_items() as $item) {
            $product = $item->get_product();
            $items[] = array(
                'id' => $product ? ($product->get_sku() ?: $product->get_id()) : $item->get_product_id(),
                'name' => $item->get_name(),
                'price' => $item->get_total() / max(1, $item->get_quantity()),
                'quantity' => $item->get_quantity(),
            );
        }

        // Facebook Pixel
        if (!empty($settings['fb_pixel_id'])) {
            ?>
            <script>
            fbq('track', 'Purchase', {
                value: <?php echo esc_js($total); ?>,
                currency: '<?php echo esc_js($currency); ?>',
                contents: <?php echo wp_json_encode($items); ?>,
                content_type: 'product',
                order_id: '<?php echo esc_js($order_id); ?>'
            });
            </script>
            <?php
        }

        // TikTok Pixel
        if (!empty($settings['tiktok_pixel_id'])) {
            ?>
            <script>
            ttq.track('CompletePayment', {
                value: <?php echo esc_js($total); ?>,
                currency: '<?php echo esc_js($currency); ?>',
                contents: <?php echo wp_json_encode($items); ?>,
                order_id: '<?php echo esc_js($order_id); ?>'
            });
            </script>
            <?php
        }

        // GA4
        if (!empty($settings['ga4_measurement_id'])) {
            ?>
            <script>
            gtag('event', 'purchase', {
                transaction_id: '<?php echo esc_js($order_id); ?>',
                value: <?php echo esc_js($total); ?>,
                currency: '<?php echo esc_js($currency); ?>',
                items: <?php echo wp_json_encode($items); ?>,
                tax: <?php echo esc_js($order->get_total_tax()); ?>,
                shipping: <?php echo esc_js($order->get_shipping_total()); ?>
            });
            </script>
            <?php
        }
    }
}

// 初始化
new Nuotao_Social_Tracking();
