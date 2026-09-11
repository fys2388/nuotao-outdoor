<?php
/**
 * Plugin Name: Nuotao B2B Footer Link
 * Description: 在 B2C 站页脚 About Us 列添加 B2B Wholesale 申请和登录链接
 * Version: 1.1
 */

add_action('wp_footer', function() {
    ?>
    <script>
    (function() {
        function addB2BLinks() {
            // 找到页脚中所有列
            var footer = document.querySelector('.nuotao-footer, footer, .site-footer');
            if (!footer) return false;

            // 找到包含 "Privacy Policy" 的列（About Us 列）
            var allLinks = footer.querySelectorAll('a');
            var privacyLink = null;
            for (var i = 0; i < allLinks.length; i++) {
                if (allLinks[i].textContent.trim() === 'Privacy Policy') {
                    privacyLink = allLinks[i];
                    break;
                }
            }
            if (!privacyLink) return false;

            // 找到该列的 ul 容器
            var ul = privacyLink.closest('ul');
            if (!ul) return false;

            // 检查是否已添加
            if (ul.querySelector('.nuotao-b2b-footer-link')) return true;

            // 创建 Wholesale 链接
            var li1 = document.createElement('li');
            li1.className = 'nuotao-b2b-footer-link';
            li1.style.marginBottom = '10px';
            li1.innerHTML = '<a href="https://b2b.nuotaooutdoor.com/#/apply" target="_blank" rel="noopener" '
                + 'style="color:#b0b8c8;text-decoration:none;font-size:13px;display:inline-flex;align-items:center;gap:6px;">'
                + '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;">'
                + '<path d="M20 7h-9M14 17H5M17 17a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM7 7a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/>'
                + '</svg>Wholesale / B2B Apply</a>';

            // 创建 B2B Login 链接
            var li2 = document.createElement('li');
            li2.className = 'nuotao-b2b-footer-link';
            li2.style.marginBottom = '10px';
            li2.innerHTML = '<a href="https://b2b.nuotaooutdoor.com/#/login" target="_blank" rel="noopener" '
                + 'style="color:#b0b8c8;text-decoration:none;font-size:13px;display:inline-flex;align-items:center;gap:6px;">'
                + '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;">'
                + '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/>'
                + '</svg>B2B Partner Login</a>';

            ul.appendChild(li1);
            ul.appendChild(li2);
            return true;
        }

        // 立即尝试 + 延迟重试
        if (!addB2BLinks()) {
            var attempts = 0;
            var interval = setInterval(function() {
                if (addB2BLinks() || attempts++ > 25) {
                    clearInterval(interval);
                }
            }, 300);
        }
    })();
    </script>
    <?php
}, 100);
