#!/usr/bin/env python3
"""验证P0三件套导入"""
import sys
sys.path.insert(0, '/opt/nuotao/backend')

try:
    from app.services.product_analysis_service import *
    from app.services.prompt_generator_service import *
    from app.api.v1.endpoints.product_analysis import router
    print('All imports OK')
    print('Router prefix:', router.prefix)
    
    # 测试Prompt生成
    from app.services.prompt_generator_service import generate_full_prompt, get_prompt_generator_status
    status = get_prompt_generator_status()
    print('Prompt generator status:', status['status'])
    print('Supported page types:', len(status['supported_page_types']))
    
    test_report = {
        'product_name': '测试产品',
        'brand_name': 'TestBrand',
        'product_category': '测试类目',
        'product_appearance': '测试外观',
        'material_craft': '测试材质',
        'product_color': '白色',
        'product_dimensions': '10x10x10cm',
        'product_capacity': '1L',
        'applicable_target': '测试对象',
        'core_selling_points': ['卖点1', '卖点2'],
        'product_features': ['功能1', '功能2'],
        'target_audience': '测试人群',
        'usage_scenarios': ['场景1', '场景2'],
        'visual_style': '极简',
        'primary_colors': ['白色', '黑色'],
        'extendable_pages': ['brand_scene', 'product_hero'],
        'product_description': '测试描述',
        'quality_assurance': '测试保障',
    }
    result = generate_full_prompt(test_report, page_type='brand_scene')
    print('Prompt generation success:', result['success'])
    print('Prompt length:', result['data']['metadata']['prompt_length'])
    print('ALL TESTS PASSED')
    
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
