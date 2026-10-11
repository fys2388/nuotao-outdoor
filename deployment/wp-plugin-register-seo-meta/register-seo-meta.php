<?php
/**
 * Plugin Name: Nuotao SEO Meta REST Registration
 * Plugin URI: https://nuotaooutdoor.com
 * Description: Register Rank Math SEO meta fields for WordPress REST API access
 * Version: 1.0.0
 * Author: Nuotao AI OS
 * License: GPL v2 or later
 * Text Domain: nuotao-seo-meta
 *
 * 功能: 让 Rank Math 的 SEO meta 字段通过 REST API 可访问和更新
 * 
 * 部署后访问: /wp-json/nuotao/v1/seo/{post_id}
 */

// 防止直接访问
if (!defined('ABSPATH')) {
    exit;
}

// 激活钩子
register_activation_hook(__FILE__, 'nuotao_seo_meta_activate');

/**
 * 插件激活时注册 meta 字段
 */
function nuotao_seo_meta_activate() {
    nuotao_register_seo_meta_fields();
}

/**
 * 注册 Rank Math SEO meta 字段
 */
function nuotao_register_seo_meta_fields() {
    $post_types = ['product', 'post', 'page'];
    
    $meta_fields = [
        '_rank_math_title_web' => ['title' => 'SEO Title', 'type' => 'string'],
        '_rank_math_description_web' => ['title' => 'Meta Description', 'type' => 'string'],
        '_rank_math_focus_keyphrase' => ['title' => 'Focus Keyword', 'type' => 'string'],
        '_rank_math_robots_noindex_web' => ['title' => 'Noindex', 'type' => 'boolean'],
        '_rank_math_robots_nofollow_web' => ['title' => 'Nofollow', 'type' => 'boolean'],
        '_rank_math_canonical_url_web' => ['title' => 'Canonical URL', 'type' => 'string'],
        '_rank_math_social_title_web' => ['title' => 'Social Title', 'type' => 'string'],
        '_rank_math_social_description_web' => ['title' => 'Social Description', 'type' => 'string'],
        '_rank_math_facebook_title_web' => ['title' => 'Facebook Title', 'type' => 'string'],
        '_rank_math_facebook_description_web' => ['title' => 'Facebook Description', 'type' => 'string'],
        '_rank_math_twitter_title_web' => ['title' => 'Twitter Title', 'type' => 'string'],
        '_rank_math_twitter_description_web' => ['title' => 'Twitter Description', 'type' => 'string'],
    ];
    
    foreach ($post_types as $post_type) {
        foreach ($meta_fields as $key => $field_info) {
            register_post_meta($post_type, $key, [
                'show_in_rest' => true,
                'single' => true,
                'type' => $field_info['type'],
                'description' => $field_info['title'],
                'auth_callback' => function () {
                    return current_user_can('edit_posts');
                },
            ]);
        }
    }
}

// 在 init 钩子中注册 meta 字段
add_action('init', 'nuotao_register_seo_meta_fields', 99);

/**
 * REST API 端点注册
 */
add_action('rest_api_init', function () {
    // GET 端点：获取 SEO 数据
    register_rest_route('nuotao/v1', '/seo/(?P<post_id>\d+)', [
        'methods' => 'GET',
        'callback' => 'nuotao_get_seo_data',
        'permission_callback' => function () {
            return current_user_can('edit_posts');
        },
        'args' => [
            'post_id' => [
                'validate_callback' => function ($param) {
                    return is_numeric($param);
                },
            ],
        ],
    ]);
    
    // POST 端点：更新 SEO 数据
    register_rest_route('nuotao/v1', '/seo/(?P<post_id>\d+)', [
        'methods' => 'POST',
        'callback' => 'nuotao_update_seo_data',
        'permission_callback' => function () {
            return current_user_can('edit_posts');
        },
        'args' => [
            'post_id' => [
                'validate_callback' => function ($param) {
                    return is_numeric($param);
                },
            ],
        ],
    ]);
});

/**
 * 获取文章的 SEO 数据
 */
function nuotao_get_seo_data(WP_REST_Request $request) {
    $post_id = intval($request['post_id']);
    $post = get_post($post_id);
    
    if (!$post) {
        return new WP_REST_Response(['error' => 'Post not found'], 404);
    }
    
    $seo_data = [
        'id' => $post_id,
        'type' => $post->post_type,
        'title' => $post->post_title,
        'slug' => $post->post_name,
        'seo_title' => get_post_meta($post_id, '_rank_math_title_web', true),
        'meta_description' => get_post_meta($post_id, '_rank_math_description_web', true),
        'focus_keyword' => get_post_meta($post_id, '_rank_math_focus_keyphrase', true),
        'noindex' => get_post_meta($post_id, '_rank_math_robots_noindex_web', true) == '1',
        'excerpt' => $post->post_excerpt,
        'link' => get_permalink($post_id),
    ];
    
    return new WP_REST_Response($seo_data, 200);
}

/**
 * 更新文章的 SEO 数据
 */
function nuotao_update_seo_data(WP_REST_Request $request) {
    $post_id = intval($request['post_id']);
    $post = get_post($post_id);
    
    if (!$post) {
        return new WP_REST_Response(['error' => 'Post not found'], 404);
    }
    
    $updated = [];
    
    // 更新 SEO 标题
    if ($request->has_param('seo_title')) {
        $result = update_post_meta($post_id, '_rank_math_title_web', $request['seo_title']);
        $updated['seo_title'] = $result;
    }
    
    // 更新 Meta 描述
    if ($request->has_param('meta_description')) {
        $result = update_post_meta($post_id, '_rank_math_description_web', $request['meta_description']);
        $updated['meta_description'] = $result;
    }
    
    // 更新焦点关键词
    if ($request->has_param('focus_keyword')) {
        $result = update_post_meta($post_id, '_rank_math_focus_keyphrase', $request['focus_keyword']);
        $updated['focus_keyword'] = $result;
    }
    
    // 更新 Noindex
    if ($request->has_param('noindex')) {
        $value = $request['noindex'] ? '1' : '0';
        $result = update_post_meta($post_id, '_rank_math_robots_noindex_web', $value);
        $updated['noindex'] = $result;
    }
    
    // 更新 Excerpt (fallback)
    if ($request->has_param('excerpt')) {
        $result = wp_update_post([
            'ID' => $post_id,
            'post_excerpt' => $request['excerpt'],
        ]);
        $updated['excerpt'] = $result;
    }
    
    return new WP_REST_Response([
        'success' => true,
        'post_id' => $post_id,
        'updated' => $updated,
    ], 200);
}

/**
 * 插件管理页面
 */
add_action('admin_menu', function () {
    add_management_page(
        'Nuotao SEO Meta',
        'Nuotao SEO Meta',
        'manage_options',
        'nuotao-seo-meta',
        'nuotao_seo_meta_admin_page'
    );
});

function nuotao_seo_meta_admin_page() {
    ?>
    <div class="wrap">
        <h1>Nuotao SEO Meta REST Registration</h1>
        <p>插件已激活！Rank Math SEO meta 字段已通过 REST API 注册。</p>
        
        <h2>API 端点</h2>
        <ul>
            <li>GET /wp-json/nuotao/v1/seo/{post_id} - 获取 SEO 数据</li>
            <li>POST /wp-json/nuotao/v1/seo/{post_id} - 更新 SEO 数据</li>
        </ul>
        
        <h2>测试</h2>
        <p>使用 Application Password 认证：</p>
        <code>curl -X GET https://nuotaooutdoor.com/wp-json/nuotao/v1/seo/2372 -u "user:password"</code>
        
        <h2>注册的 Meta 字段</h2>
        <ul>
            <li>_rank_math_title_web - SEO Title</li>
            <li>_rank_math_description_web - Meta Description</li>
            <li>_rank_math_focus_keyphrase - Focus Keyword</li>
            <li>_rank_math_robots_noindex_web - Noindex</li>
        </ul>
    </div>
    <?php
}
