<?php
/**
 * 分享按钮类
 *
 * @package Nuotao_Social_Enhancements
 */

if (!defined('ABSPATH')) {
    exit;
}

/**
 * 分享按钮类
 */
class Nuotao_Share_Buttons {

    /**
     * 构造函数
     */
    public function __construct() {
        // 商品页
        add_action('woocommerce_after_single_product_summary', array($this, 'render_product_share'), 25);

        // 博客文章
        add_filter('the_content', array($this, 'render_post_share'));

        // 浮动侧边栏
        add_action('wp_footer', array($this, 'render_floating_share'), 15);
    }

    /**
     * 检查是否在商品页
     */
    private function is_product_page() {
        return function_exists('is_product') && is_product();
    }

    /**
     * 检查是否在博客文章页
     */
    private function is_blog_post() {
        return is_singular('post') && !is_page();
    }

    /**
     * 获取分享 URL
     */
    private function get_share_url($platform, $url, $title, $image = '') {
        $url = rawurlencode($url);
        $title = rawurlencode($title);
        $image = rawurlencode($image);

        $urls = array(
            'facebook' => "https://www.facebook.com/sharer/sharer.php?u={$url}",
            'twitter' => "https://twitter.com/intent/tweet?url={$url}&text={$title}",
            'pinterest' => "https://pinterest.com/pin/create/button/?url={$url}&media={$image}&description={$title}",
            'linkedin' => "https://www.linkedin.com/sharing/share-offsite/?url={$url}",
            'whatsapp' => "https://wa.me/?text={$title}%20{$url}",
            'email' => "mailto:?subject={$title}&body={$url}",
        );

        return isset($urls[$platform]) ? $urls[$platform] : '';
    }

    /**
     * 获取分享按钮 HTML
     */
    private function get_share_buttons_html($position = 'bottom') {
        $settings = Nuotao_Social_Enhancements::get_settings();

        // 检查位置设置
        $share_position = $settings['share_position'];
        if ('bottom' === $position && 'floating' === $share_position) {
            return '';
        }
        if ('floating' === $position && 'bottom' === $share_position) {
            return '';
        }

        $platforms = $settings['share_platforms'];
        if (empty($platforms)) {
            return '';
        }

        // 获取当前页面信息
        global $post;
        $url = get_permalink();
        $title = get_the_title();
        $image = '';

        if (has_post_thumbnail()) {
            $image = get_the_post_thumbnail_url($post->ID, 'full');
        }

        // 商品特殊处理
        if ($this->is_product_page()) {
            global $product;
            if ($product) {
                $title = $product->get_name();
                $image = wp_get_attachment_url($product->get_image_id());
            }
        }

        $classes = sprintf('nuotao-share-buttons nuotao-share-%s', esc_attr($position));

        $html = sprintf('<div class="%s">', esc_attr($classes));
        $html .= '<span class="nuotao-share-label">' . esc_html__('Share', 'nuotao-social') . '</span>';
        $html .= '<div class="nuotao-share-list">';

        foreach ($platforms as $platform) {
            if ('copy' === $platform) {
                $html .= $this->get_copy_button();
            } else {
                $share_url = $this->get_share_url($platform, $url, $title, $image);
                if (!empty($share_url)) {
                    $html .= sprintf(
                        '<a href="%s" class="nuotao-share-btn nuotao-share-%s" target="_blank" rel="noopener noreferrer" aria-label="%s" title="%s" data-url="%s">',
                        esc_url($share_url),
                        esc_attr($platform),
                        esc_attr(sprintf(__('Share on %s', 'nuotao-social'), ucfirst($platform))),
                        esc_attr(ucfirst($platform)),
                        esc_url($url)
                    );
                    $html .= $this->get_platform_icon($platform);
                    $html .= '</a>';
                }
            }
        }

        $html .= '</div>';
        $html .= '</div>';

        return $html;
    }

    /**
     * 获取复制链接按钮
     */
    private function get_copy_button() {
        $url = get_permalink();
        return sprintf(
            '<button type="button" class="nuotao-share-btn nuotao-share-copy" aria-label="%s" title="%s" data-url="%s" onclick="nuotaoSocialCopyLink(this)">',
            esc_attr__('Copy link', 'nuotao-social'),
            esc_attr__('Copy link', 'nuotao-social'),
            esc_url($url)
        ) . $this->get_platform_icon('copy') . '</button>';
    }

    /**
     * 渲染商品页分享按钮
     */
    public function render_product_share() {
        $settings = Nuotao_Social_Enhancements::get_settings();

        if ('yes' !== $settings['share_on_product']) {
            return;
        }

        if (!$this->is_product_page()) {
            return;
        }

        echo $this->get_share_buttons_html('bottom');
    }

    /**
     * 渲染博客文章分享按钮
     */
    public function render_post_share($content) {
        $settings = Nuotao_Social_Enhancements::get_settings();

        if ('yes' !== $settings['share_on_post']) {
            return $content;
        }

        if (!$this->is_blog_post()) {
            return $content;
        }

        // 只在主循环中
        if (!in_the_loop() || !is_main_query()) {
            return $content;
        }

        $share_html = $this->get_share_buttons_html('bottom');
        return $content . $share_html;
    }

    /**
     * 渲染浮动分享侧边栏
     */
    public function render_floating_share() {
        $settings = Nuotao_Social_Enhancements::get_settings();

        // 检查是否在商品页或博客页
        $show = false;
        if ($this->is_product_page() && 'yes' === $settings['share_on_product']) {
            $show = true;
        }
        if ($this->is_blog_post() && 'yes' === $settings['share_on_post']) {
            $show = true;
        }

        if (!$show) {
            return;
        }

        echo $this->get_share_buttons_html('floating');
    }

    /**
     * 获取平台图标
     */
    private function get_platform_icon($platform) {
        $icons = array(
            'facebook' => '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>',
            'twitter' => '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>',
            'pinterest' => '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12.017 0C5.396 0 .029 5.367.029 11.987c0 5.079 3.158 9.417 7.618 11.162-.105-.949-.199-2.403.041-3.439.219-.937 1.406-5.957 1.406-5.957s-.359-.72-.359-1.781c0-1.663.967-2.911 2.168-2.911 1.024 0 1.518.769 1.518 1.688 0 1.029-.653 2.567-.992 3.992-.285 1.193.6 2.165 1.775 2.165 2.128 0 3.768-2.245 3.768-5.487 0-2.861-2.063-4.869-5.008-4.869-3.41 0-5.409 2.562-5.409 5.199 0 1.033.394 2.143.889 2.741.099.12.112.225.085.345-.09.375-.293 1.199-.334 1.363-.053.225-.172.271-.401.165-1.495-.69-2.433-2.878-2.433-4.646 0-3.776 2.748-7.252 7.92-7.252 4.158 0 7.392 2.967 7.392 6.923 0 4.135-2.607 7.462-6.233 7.462-1.214 0-2.354-.629-2.758-1.379l-.749 2.848c-.269 1.045-1.004 2.352-1.498 3.146 1.123.345 2.306.535 3.55.535 6.607 0 11.985-5.365 11.985-11.987C23.97 5.39 18.592.026 12.017.026z"/></svg>',
            'linkedin' => '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>',
            'whatsapp' => '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>',
            'email' => '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M24 5.457v13.909c0 .904-.732 1.636-1.636 1.636h-3.819V11.73L12 16.64l-6.545-4.91v9.273H1.636A1.636 1.636 0 010 19.366V5.457c0-2.023 2.309-3.178 3.927-1.964L5.455 4.64 12 9.548l6.545-4.91 1.528-1.145C21.69 2.28 24 3.434 24 5.457z"/></svg>',
            'copy' => '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>',
        );

        return isset($icons[$platform]) ? $icons[$platform] : '';
    }
}

// 初始化
new Nuotao_Share_Buttons();
