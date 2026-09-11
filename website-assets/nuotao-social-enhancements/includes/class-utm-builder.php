<?php
/**
 * UTM 链接生成器类
 *
 * @package Nuotao_Social_Enhancements
 */

if (!defined('ABSPATH')) {
    exit;
}

/**
 * UTM 链接生成器类
 */
class Nuotao_Social_UTM_Builder {

    /**
     * 构造函数
     */
    public function __construct() {
        // AJAX 处理
        add_action('wp_ajax_nuotao_generate_utm', array($this, 'ajax_generate_utm'));
    }

    /**
     * 渲染 UTM 生成器
     */
    public static function render_builder() {
        ?>
        <div class="nuotao-utm-builder">
            <table class="form-table" role="presentation">
                <tr>
                    <th scope="row"><label for="utm_url"><?php esc_html_e('Website URL', 'nuotao-social'); ?></label></th>
                    <td>
                        <input type="url" id="utm_url" class="regular-text" placeholder="https://nuotaooutdoor.com/product/example" value="<?php echo esc_attr(home_url('/')); ?>">
                        <p class="description"><?php esc_html_e('The base URL to add UTM parameters to.', 'nuotao-social'); ?></p>
                    </td>
                </tr>
                <tr>
                    <th scope="row"><label for="utm_source"><?php esc_html_e('Campaign Source', 'nuotao-social'); ?> <span class="required">*</span></label></th>
                    <td>
                        <select id="utm_source" class="regular-text">
                            <option value=""><?php esc_html_e('— Select —', 'nuotao-social'); ?></option>
                            <option value="facebook">Facebook</option>
                            <option value="instagram">Instagram</option>
                            <option value="tiktok">TikTok</option>
                            <option value="pinterest">Pinterest</option>
                            <option value="youtube">YouTube</option>
                            <option value="twitter">X (Twitter)</option>
                            <option value="google">Google</option>
                            <option value="email">Email</option>
                            <option value="newsletter">Newsletter</option>
                            <option value="affiliate">Affiliate</option>
                            <option value="referral">Referral</option>
                            <option value="direct">Direct</option>
                            <option value="other"><?php esc_html_e('Other (custom)', 'nuotao-social'); ?></option>
                        </select>
                        <input type="text" id="utm_source_custom" class="regular-text" style="display:none;margin-top:5px;" placeholder="<?php esc_attr_e('Enter custom source', 'nuotao-social'); ?>">
                        <p class="description"><?php esc_html_e('The referrer: e.g. facebook, instagram, google, email.', 'nuotao-social'); ?></p>
                    </td>
                </tr>
                <tr>
                    <th scope="row"><label for="utm_medium"><?php esc_html_e('Campaign Medium', 'nuotao-social'); ?> <span class="required">*</span></label></th>
                    <td>
                        <select id="utm_medium" class="regular-text">
                            <option value=""><?php esc_html_e('— Select —', 'nuotao-social'); ?></option>
                            <option value="social"><?php esc_html_e('Social Media', 'nuotao-social'); ?></option>
                            <option value="cpc"><?php esc_html_e('Paid Search (CPC)', 'nuotao-social'); ?></option>
                            <option value="organic"><?php esc_html_e('Organic Search', 'nuotao-social'); ?></option>
                            <option value="email"><?php esc_html_e('Email', 'nuotao-social'); ?></option>
                            <option value="referral"><?php esc_html_e('Referral', 'nuotao-social'); ?></option>
                            <option value="display"><?php esc_html_e('Display Ads', 'nuotao-social'); ?></option>
                            <option value="video"><?php esc_html_e('Video', 'nuotao-social'); ?></option>
                            <option value="affiliate"><?php esc_html_e('Affiliate', 'nuotao-social'); ?></option>
                            <option value="direct"><?php esc_html_e('Direct', 'nuotao-social'); ?></option>
                            <option value="other"><?php esc_html_e('Other (custom)', 'nuotao-social'); ?></option>
                        </select>
                        <input type="text" id="utm_medium_custom" class="regular-text" style="display:none;margin-top:5px;" placeholder="<?php esc_attr_e('Enter custom medium', 'nuotao-social'); ?>">
                        <p class="description"><?php esc_html_e('The marketing medium: e.g. social, cpc, email, referral.', 'nuotao-social'); ?></p>
                    </td>
                </tr>
                <tr>
                    <th scope="row"><label for="utm_campaign"><?php esc_html_e('Campaign Name', 'nuotao-social'); ?> <span class="required">*</span></label></th>
                    <td>
                        <input type="text" id="utm_campaign" class="regular-text" placeholder="<?php esc_attr_e('e.g. summer_sale_2026, product_launch, black_friday', 'nuotao-social'); ?>">
                        <p class="description"><?php esc_html_e('The campaign name for tracking: e.g. summer_sale, product_launch.', 'nuotao-social'); ?></p>
                    </td>
                </tr>
                <tr>
                    <th scope="row"><label for="utm_term"><?php esc_html_e('Campaign Term', 'nuotao-social'); ?> (<?php esc_html_e('optional', 'nuotao-social'); ?>)</label></th>
                    <td>
                        <input type="text" id="utm_term" class="regular-text" placeholder="<?php esc_attr_e('e.g. camping_gear, outdoor_equipment', 'nuotao-social'); ?>">
                        <p class="description"><?php esc_html_e('Identify the paid keywords for this campaign.', 'nuotao-social'); ?></p>
                    </td>
                </tr>
                <tr>
                    <th scope="row"><label for="utm_content"><?php esc_html_e('Campaign Content', 'nuotao-social'); ?> (<?php esc_html_e('optional', 'nuotao-social'); ?>)</label></th>
                    <td>
                        <input type="text" id="utm_content" class="regular-text" placeholder="<?php esc_attr_e('e.g. banner_ad, text_link, video_v1', 'nuotao-social'); ?>">
                        <p class="description"><?php esc_html_e('Used to differentiate similar content within the same campaign.', 'nuotao-social'); ?></p>
                    </td>
                </tr>
            </table>

            <p class="submit">
                <button type="button" class="button button-primary" onclick="nuotaoGenerateUTM()"><?php esc_html_e('Generate UTM Link', 'nuotao-social'); ?></button>
            </p>

            <div id="utm_result" style="display:none;margin-top:20px;padding:15px;background:#f9f9f9;border:1px solid #ddd;border-radius:4px;">
                <h4 style="margin-top:0;"><?php esc_html_e('Generated UTM Link', 'nuotao-social'); ?></h4>
                <div style="display:flex;gap:10px;align-items:center;">
                    <input type="text" id="utm_result_url" class="regular-text" readonly style="flex:1;background:#fff;">
                    <button type="button" class="button" onclick="nuotaoCopyUTM()"><?php esc_html_e('Copy', 'nuotao-social'); ?></button>
                </div>
                <p id="utm_result_msg" style="margin-top:10px;color:green;display:none;"><?php esc_html_e('Link copied to clipboard!', 'nuotao-social'); ?></p>
            </div>
        </div>

        <script type="text/javascript">
        function nuotaoGenerateUTM() {
            var url = document.getElementById('utm_url').value.trim();
            var sourceSelect = document.getElementById('utm_source');
            var source = sourceSelect.value === 'other' ? document.getElementById('utm_source_custom').value.trim() : sourceSelect.value;
            var mediumSelect = document.getElementById('utm_medium');
            var medium = mediumSelect.value === 'other' ? document.getElementById('utm_medium_custom').value.trim() : mediumSelect.value;
            var campaign = document.getElementById('utm_campaign').value.trim();
            var term = document.getElementById('utm_term').value.trim();
            var content = document.getElementById('utm_content').value.trim();

            if (!url || !source || !medium || !campaign) {
                alert('<?php esc_html_e('Please fill in all required fields (URL, Source, Medium, Campaign Name).', 'nuotao-social'); ?>');
                return;
            }

            // 构建 UTM URL
            var separator = url.indexOf('?') !== -1 ? '&' : '?';
            var utmUrl = url + separator +
                'utm_source=' + encodeURIComponent(source) +
                '&utm_medium=' + encodeURIComponent(medium) +
                '&utm_campaign=' + encodeURIComponent(campaign);

            if (term) {
                utmUrl += '&utm_term=' + encodeURIComponent(term);
            }
            if (content) {
                utmUrl += '&utm_content=' + encodeURIComponent(content);
            }

            document.getElementById('utm_result_url').value = utmUrl;
            document.getElementById('utm_result').style.display = 'block';
        }

        function nuotaoCopyUTM() {
            var input = document.getElementById('utm_result_url');
            input.select();
            document.execCommand('copy');
            var msg = document.getElementById('utm_result_msg');
            msg.style.display = 'block';
            setTimeout(function() { msg.style.display = 'none'; }, 3000);
        }

        // 显示/隐藏自定义输入框
        document.getElementById('utm_source').addEventListener('change', function() {
            document.getElementById('utm_source_custom').style.display = this.value === 'other' ? 'block' : 'none';
        });
        document.getElementById('utm_medium').addEventListener('change', function() {
            document.getElementById('utm_medium_custom').style.display = this.value === 'other' ? 'block' : 'none';
        });
        </script>
        <?php
    }

    /**
     * AJAX 生成 UTM（备用）
     */
    public function ajax_generate_utm() {
        check_ajax_referer('nuotao_social_nonce', 'nonce');

        $url = isset($_POST['url']) ? esc_url_raw(wp_unslash($_POST['url'])) : '';
        $source = isset($_POST['source']) ? sanitize_text_field(wp_unslash($_POST['source'])) : '';
        $medium = isset($_POST['medium']) ? sanitize_text_field(wp_unslash($_POST['medium'])) : '';
        $campaign = isset($_POST['campaign']) ? sanitize_text_field(wp_unslash($_POST['campaign'])) : '';
        $term = isset($_POST['term']) ? sanitize_text_field(wp_unslash($_POST['term'])) : '';
        $content = isset($_POST['content']) ? sanitize_text_field(wp_unslash($_POST['content'])) : '';

        if (empty($url) || empty($source) || empty($medium) || empty($campaign)) {
            wp_send_json_error(array('message' => 'Missing required fields'));
        }

        $separator = strpos($url, '?') !== false ? '&' : '?';
        $utm_url = $url . $separator .
            'utm_source=' . urlencode($source) .
            '&utm_medium=' . urlencode($medium) .
            '&utm_campaign=' . urlencode($campaign);

        if (!empty($term)) {
            $utm_url .= '&utm_term=' . urlencode($term);
        }
        if (!empty($content)) {
            $utm_url .= '&utm_content=' . urlencode($content);
        }

        wp_send_json_success(array('utm_url' => $utm_url));
    }
}

// 初始化
new Nuotao_Social_UTM_Builder();
