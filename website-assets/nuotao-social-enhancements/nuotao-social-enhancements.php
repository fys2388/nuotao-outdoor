<?php
/**
 * Plugin Name: Nuotao Social Enhancements
 * Plugin URI: https://nuotaooutdoor.com
 * Description: 社媒引流基础设施：页脚社媒链接、商品/博客分享按钮、Facebook/TikTok Pixel、GA4 追踪、UTM 生成器。轻量无外部依赖。
 * Version: 1.0.1
 * Author: Nuotao Outdoor
 * Author URI: https://nuotaooutdoor.com
 * License: GPL v2 or later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain: nuotao-social
 * Domain Path: /languages
 */

// 防止直接访问
if (!defined('ABSPATH')) {
    exit;
}

// 插件常量
define('NUOTAO_SOCIAL_VERSION', '1.0.1');
define('NUOTAO_SOCIAL_PLUGIN_DIR', plugin_dir_path(__FILE__));
define('NUOTAO_SOCIAL_PLUGIN_URL', plugin_dir_url(__FILE__));
define('NUOTAO_SOCIAL_PLUGIN_BASENAME', plugin_basename(__FILE__));

// 加载包含文件
require_once NUOTAO_SOCIAL_PLUGIN_DIR . 'includes/class-settings.php';
require_once NUOTAO_SOCIAL_PLUGIN_DIR . 'includes/class-social-links.php';
require_once NUOTAO_SOCIAL_PLUGIN_DIR . 'includes/class-share-buttons.php';
require_once NUOTAO_SOCIAL_PLUGIN_DIR . 'includes/class-tracking.php';
require_once NUOTAO_SOCIAL_PLUGIN_DIR . 'includes/class-utm-builder.php';

/**
 * 插件主类
 */
final class Nuotao_Social_Enhancements {

    /**
     * 单例实例
     */
    private static $instance = null;

    /**
     * 获取单例
     */
    public static function get_instance() {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }

    /**
     * 构造函数
     */
    private function __construct() {
        $this->init_hooks();
    }

    /**
     * 初始化钩子
     */
    private function init_hooks() {
        // 插件激活时执行
        register_activation_hook(__FILE__, array($this, 'activate'));

        // 插件停用时执行
        register_deactivation_hook(__FILE__, array($this, 'deactivate'));

        // 加载文本域
        add_action('plugins_loaded', array($this, 'load_textdomain'));

        // 前端资源加载
        add_action('wp_enqueue_scripts', array($this, 'enqueue_frontend_assets'));

        // 后台资源加载
        add_action('admin_enqueue_scripts', array($this, 'enqueue_admin_assets'));

        // 插件设置链接
        add_filter('plugin_action_links_' . NUOTAO_SOCIAL_PLUGIN_BASENAME, array($this, 'add_plugin_action_links'));
    }

    /**
     * 插件激活
     */
    public function activate() {
        // 设置默认选项
        $defaults = array(
            'facebook_url' => 'https://facebook.com/nuotaooutdoor',
            'instagram_url' => 'https://instagram.com/nuotaooutdoor',
            'tiktok_url' => 'https://tiktok.com/@nuotaooutdoor',
            'pinterest_url' => 'https://pinterest.com/nuotaooutdoor',
            'youtube_url' => '',
            'twitter_url' => '',
            'show_in_footer' => 'yes',
            'share_on_product' => 'yes',
            'share_on_post' => 'yes',
            'share_position' => 'both', // floating, bottom, both
            'share_platforms' => array('facebook', 'twitter', 'pinterest', 'linkedin', 'whatsapp', 'email', 'copy'),
            'fb_pixel_id' => '',
            'tiktok_pixel_id' => '',
            'ga4_measurement_id' => '',
            'exclude_admins' => 'yes',
        );

        $existing = get_option('nuotao_social_settings', array());
        $merged = wp_parse_args($existing, $defaults);
        update_option('nuotao_social_settings', $merged);

        // 刷新重写规则
        flush_rewrite_rules();
    }

    /**
     * 插件停用
     */
    public function deactivate() {
        flush_rewrite_rules();
    }

    /**
     * 加载文本域
     */
    public function load_textdomain() {
        load_plugin_textdomain('nuotao-social', false, dirname(NUOTAO_SOCIAL_PLUGIN_BASENAME) . '/languages');
    }

    /**
     * 加载前端资源
     */
    public function enqueue_frontend_assets() {
        // CSS
        wp_enqueue_style(
            'nuotao-social-frontend',
            NUOTAO_SOCIAL_PLUGIN_URL . 'assets/css/frontend.css',
            array(),
            NUOTAO_SOCIAL_VERSION
        );

        // JS（依赖 jQuery，用于监听 WooCommerce added_to_cart 事件）
        wp_enqueue_script(
            'nuotao-social-frontend',
            NUOTAO_SOCIAL_PLUGIN_URL . 'assets/js/frontend.js',
            array('jquery'),
            NUOTAO_SOCIAL_VERSION,
            true
        );

        // 传递给 JS 的数据
        $localize_data = array(
            'ajaxUrl' => admin_url('admin-ajax.php'),
            'nonce' => wp_create_nonce('nuotao_social_nonce'),
            'copyText' => __('Link copied!', 'nuotao-social'),
            'copyError' => __('Failed to copy link', 'nuotao-social'),
            'currency' => function_exists('get_woocommerce_currency') ? get_woocommerce_currency() : 'USD',
        );
        wp_localize_script('nuotao-social-frontend', 'nuotaoSocialData', $localize_data);
    }

    /**
     * 加载后台资源
     */
    public function enqueue_admin_assets($hook) {
        // 只在插件设置页加载
        if ('settings_page_nuotao-social' !== $hook) {
            return;
        }

        wp_enqueue_style(
            'nuotao-social-admin',
            NUOTAO_SOCIAL_PLUGIN_URL . 'assets/css/admin.css',
            array(),
            NUOTAO_SOCIAL_VERSION
        );

        wp_enqueue_script(
            'nuotao-social-admin',
            NUOTAO_SOCIAL_PLUGIN_URL . 'assets/js/admin.js',
            array('jquery'),
            NUOTAO_SOCIAL_VERSION,
            true
        );
    }

    /**
     * 添加插件操作链接
     */
    public function add_plugin_action_links($links) {
        $settings_link = sprintf(
            '<a href="%s">%s</a>',
            admin_url('options-general.php?page=nuotao-social'),
            __('Settings', 'nuotao-social')
        );
        array_unshift($links, $settings_link);
        return $links;
    }

    /**
     * 获取设置
     */
    public static function get_settings() {
        $defaults = array(
            'facebook_url' => '',
            'instagram_url' => '',
            'tiktok_url' => '',
            'pinterest_url' => '',
            'youtube_url' => '',
            'twitter_url' => '',
            'show_in_footer' => 'yes',
            'share_on_product' => 'yes',
            'share_on_post' => 'yes',
            'share_position' => 'both',
            'share_platforms' => array('facebook', 'twitter', 'pinterest', 'linkedin', 'whatsapp', 'email', 'copy'),
            'fb_pixel_id' => '',
            'tiktok_pixel_id' => '',
            'ga4_measurement_id' => '',
            'exclude_admins' => 'yes',
        );

        $settings = get_option('nuotao_social_settings', array());
        return wp_parse_args($settings, $defaults);
    }

    /**
     * 检查是否排除当前用户（管理员）
     */
    public static function is_excluded_user() {
        $settings = self::get_settings();
        if ('yes' === $settings['exclude_admins'] && current_user_can('manage_options')) {
            return true;
        }
        return false;
    }
}

/**
 * 初始化插件
 */
function nuotao_social_enhancements_init() {
    return Nuotao_Social_Enhancements::get_instance();
}

// 启动插件
nuotao_social_enhancements_init();
