<?php
/**
 * 设置页类
 *
 * @package Nuotao_Social_Enhancements
 */

if (!defined('ABSPATH')) {
    exit;
}

/**
 * 设置页类
 */
class Nuotao_Social_Settings {

    /**
     * 选项名称
     */
    const OPTION_NAME = 'nuotao_social_settings';

    /**
     * 构造函数
     */
    public function __construct() {
        add_action('admin_menu', array($this, 'add_admin_menu'));
        add_action('admin_init', array($this, 'register_settings'));
    }

    /**
     * 添加后台菜单
     */
    public function add_admin_menu() {
        add_options_page(
            __('Nuotao Social Settings', 'nuotao-social'),
            __('Nuotao Social', 'nuotao-social'),
            'manage_options',
            'nuotao-social',
            array($this, 'render_settings_page')
        );
    }

    /**
     * 注册设置
     */
    public function register_settings() {
        register_setting(
            'nuotao_social_group',
            self::OPTION_NAME,
            array($this, 'sanitize_settings')
        );

        // 社媒链接部分
        add_settings_section(
            'nuotao_social_links_section',
            __('Social Media Links', 'nuotao-social'),
            array($this, 'render_links_section'),
            'nuotao-social'
        );

        $this->add_url_field('facebook_url', __('Facebook URL', 'nuotao-social'));
        $this->add_url_field('instagram_url', __('Instagram URL', 'nuotao-social'));
        $this->add_url_field('tiktok_url', __('TikTok URL', 'nuotao-social'));
        $this->add_url_field('pinterest_url', __('Pinterest URL', 'nuotao-social'));
        $this->add_url_field('youtube_url', __('YouTube URL', 'nuotao-social'));
        $this->add_url_field('twitter_url', __('X (Twitter) URL', 'nuotao-social'));

        // 页脚显示
        add_settings_field(
            'show_in_footer',
            __('Show in Footer', 'nuotao-social'),
            array($this, 'render_checkbox_field'),
            'nuotao-social',
            'nuotao_social_links_section',
            array('field' => 'show_in_footer')
        );

        // 分享按钮部分
        add_settings_section(
            'nuotao_social_share_section',
            __('Share Buttons', 'nuotao-social'),
            array($this, 'render_share_section'),
            'nuotao-social'
        );

        add_settings_field(
            'share_on_product',
            __('Show on Products', 'nuotao-social'),
            array($this, 'render_checkbox_field'),
            'nuotao-social',
            'nuotao_social_share_section',
            array('field' => 'share_on_product')
        );

        add_settings_field(
            'share_on_post',
            __('Show on Blog Posts', 'nuotao-social'),
            array($this, 'render_checkbox_field'),
            'nuotao-social',
            'nuotao_social_share_section',
            array('field' => 'share_on_post')
        );

        add_settings_field(
            'share_position',
            __('Button Position', 'nuotao-social'),
            array($this, 'render_select_field'),
            'nuotao-social',
            'nuotao_social_share_section',
            array(
                'field' => 'share_position',
                'options' => array(
                    'floating' => __('Floating Sidebar', 'nuotao-social'),
                    'bottom' => __('Bottom of Content', 'nuotao-social'),
                    'both' => __('Both', 'nuotao-social'),
                ),
            )
        );

        add_settings_field(
            'share_platforms',
            __('Share Platforms', 'nuotao-social'),
            array($this, 'render_checkbox_group_field'),
            'nuotao-social',
            'nuotao_social_share_section',
            array(
                'field' => 'share_platforms',
                'options' => array(
                    'facebook' => 'Facebook',
                    'twitter' => 'X (Twitter)',
                    'pinterest' => 'Pinterest',
                    'linkedin' => 'LinkedIn',
                    'whatsapp' => 'WhatsApp',
                    'email' => 'Email',
                    'copy' => __('Copy Link', 'nuotao-social'),
                ),
            )
        );

        // 追踪代码部分
        add_settings_section(
            'nuotao_social_tracking_section',
            __('Tracking Pixels & Analytics', 'nuotao-social'),
            array($this, 'render_tracking_section'),
            'nuotao-social'
        );

        $this->add_text_field('fb_pixel_id', __('Facebook Pixel ID', 'nuotao-social'), __('e.g. 1234567890123456', 'nuotao-social'));
        $this->add_text_field('tiktok_pixel_id', __('TikTok Pixel ID', 'nuotao-social'), __('e.g. C1234567890', 'nuotao-social'));
        $this->add_text_field('ga4_measurement_id', __('GA4 Measurement ID', 'nuotao-social'), __('e.g. G-XXXXXXXXXX', 'nuotao-social'));

        add_settings_field(
            'exclude_admins',
            __('Exclude Administrators', 'nuotao-social'),
            array($this, 'render_checkbox_field'),
            'nuotao-social',
            'nuotao_social_tracking_section',
            array('field' => 'exclude_admins')
        );
    }

    /**
     * 添加 URL 字段
     */
    private function add_url_field($field, $label) {
        add_settings_field(
            $field,
            $label,
            array($this, 'render_url_field'),
            'nuotao-social',
            'nuotao_social_links_section',
            array('field' => $field)
        );
    }

    /**
     * 添加文本字段
     */
    private function add_text_field($field, $label, $placeholder = '') {
        add_settings_field(
            $field,
            $label,
            array($this, 'render_text_field'),
            'nuotao-social',
            'nuotao_social_tracking_section',
            array('field' => $field, 'placeholder' => $placeholder)
        );
    }

    /**
     * 渲染设置页
     */
    public function render_settings_page() {
        if (!current_user_can('manage_options')) {
            return;
        }
        ?>
        <div class="wrap nuotao-social-settings">
            <h1><?php echo esc_html(get_admin_page_title()); ?></h1>
            <p class="description"><?php esc_html_e('Configure social media links, share buttons, and tracking pixels for your store.', 'nuotao-social'); ?></p>

            <form method="post" action="options.php">
                <?php
                settings_fields('nuotao_social_group');
                do_settings_sections('nuotao-social');
                submit_button();
                ?>
            </form>

            <div class="nuotao-social-utm-builder">
                <h2><?php esc_html_e('UTM Link Builder', 'nuotao-social'); ?></h2>
                <p class="description"><?php esc_html_e('Generate UTM-tagged URLs for social media campaigns.', 'nuotao-social'); ?></p>
                <?php Nuotao_Social_UTM_Builder::render_builder(); ?>
            </div>
        </div>
        <?php
    }

    /**
     * 渲染社媒链接部分说明
     */
    public function render_links_section() {
        echo '<p>' . esc_html__('Enter your social media profile URLs. Leave blank to hide a platform.', 'nuotao-social') . '</p>';
    }

    /**
     * 渲染分享按钮部分说明
     */
    public function render_share_section() {
        echo '<p>' . esc_html__('Configure share buttons appearance on product pages and blog posts.', 'nuotao-social') . '</p>';
    }

    /**
     * 渲染追踪部分说明
     */
    public function render_tracking_section() {
        echo '<p>' . esc_html__('Add tracking pixels and analytics IDs. Leave blank to disable a tracking tool.', 'nuotao-social') . '</p>';
    }

    /**
     * 渲染 URL 字段
     */
    public function render_url_field($args) {
        $settings = Nuotao_Social_Enhancements::get_settings();
        $field = $args['field'];
        $value = isset($settings[$field]) ? $settings[$field] : '';
        echo sprintf(
            '<input type="url" name="%s[%s]" value="%s" class="regular-text" placeholder="https://">',
            esc_attr(self::OPTION_NAME),
            esc_attr($field),
            esc_attr($value)
        );
    }

    /**
     * 渲染文本字段
     */
    public function render_text_field($args) {
        $settings = Nuotao_Social_Enhancements::get_settings();
        $field = $args['field'];
        $placeholder = isset($args['placeholder']) ? $args['placeholder'] : '';
        $value = isset($settings[$field]) ? $settings[$field] : '';
        echo sprintf(
            '<input type="text" name="%s[%s]" value="%s" class="regular-text" placeholder="%s">',
            esc_attr(self::OPTION_NAME),
            esc_attr($field),
            esc_attr($value),
            esc_attr($placeholder)
        );
    }

    /**
     * 渲染复选框字段
     */
    public function render_checkbox_field($args) {
        $settings = Nuotao_Social_Enhancements::get_settings();
        $field = $args['field'];
        $value = isset($settings[$field]) ? $settings[$field] : 'no';
        echo sprintf(
            '<label><input type="checkbox" name="%s[%s]" value="yes" %s> %s</label>',
            esc_attr(self::OPTION_NAME),
            esc_attr($field),
            checked($value, 'yes', false),
            esc_html__('Enabled', 'nuotao-social')
        );
    }

    /**
     * 渲染下拉选择字段
     */
    public function render_select_field($args) {
        $settings = Nuotao_Social_Enhancements::get_settings();
        $field = $args['field'];
        $value = isset($settings[$field]) ? $settings[$field] : '';
        $options = isset($args['options']) ? $args['options'] : array();

        echo sprintf('<select name="%s[%s]">', esc_attr(self::OPTION_NAME), esc_attr($field));
        foreach ($options as $key => $label) {
            echo sprintf(
                '<option value="%s" %s>%s</option>',
                esc_attr($key),
                selected($value, $key, false),
                esc_html($label)
            );
        }
        echo '</select>';
    }

    /**
     * 渲染复选框组字段
     */
    public function render_checkbox_group_field($args) {
        $settings = Nuotao_Social_Enhancements::get_settings();
        $field = $args['field'];
        $selected = isset($settings[$field]) ? $settings[$field] : array();
        $options = isset($args['options']) ? $args['options'] : array();

        echo '<div class="nuotao-checkbox-group">';
        foreach ($options as $key => $label) {
            $checked = in_array($key, (array) $selected, true) ? 'checked' : '';
            echo sprintf(
                '<label style="display:inline-block;margin-right:15px;margin-bottom:5px;"><input type="checkbox" name="%s[%s][]" value="%s" %s> %s</label>',
                esc_attr(self::OPTION_NAME),
                esc_attr($field),
                esc_attr($key),
                $checked,
                esc_html($label)
            );
        }
        echo '</div>';
    }

    /**
     * 清理设置
     */
    public function sanitize_settings($input) {
        $sanitized = array();

        // URL 字段
        $url_fields = array('facebook_url', 'instagram_url', 'tiktok_url', 'pinterest_url', 'youtube_url', 'twitter_url');
        foreach ($url_fields as $field) {
            if (isset($input[$field]) && !empty($input[$field])) {
                $sanitized[$field] = esc_url_raw($input[$field]);
            } else {
                $sanitized[$field] = '';
            }
        }

        // 文本字段
        $text_fields = array('fb_pixel_id', 'tiktok_pixel_id', 'ga4_measurement_id');
        foreach ($text_fields as $field) {
            if (isset($input[$field])) {
                $sanitized[$field] = sanitize_text_field($input[$field]);
            } else {
                $sanitized[$field] = '';
            }
        }

        // 复选框字段
        $checkbox_fields = array('show_in_footer', 'share_on_product', 'share_on_post', 'exclude_admins');
        foreach ($checkbox_fields as $field) {
            $sanitized[$field] = isset($input[$field]) && 'yes' === $input[$field] ? 'yes' : 'no';
        }

        // 选择字段
        if (isset($input['share_position']) && in_array($input['share_position'], array('floating', 'bottom', 'both'), true)) {
            $sanitized['share_position'] = $input['share_position'];
        } else {
            $sanitized['share_position'] = 'both';
        }

        // 复选框组
        if (isset($input['share_platforms']) && is_array($input['share_platforms'])) {
            $valid_platforms = array('facebook', 'twitter', 'pinterest', 'linkedin', 'whatsapp', 'email', 'copy');
            $sanitized['share_platforms'] = array_values(array_intersect($input['share_platforms'], $valid_platforms));
        } else {
            $sanitized['share_platforms'] = array();
        }

        return $sanitized;
    }
}

// 初始化
new Nuotao_Social_Settings();
