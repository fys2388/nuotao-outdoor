"""Test the new image generation workflow - English only"""

import re
from app.services.image_prompt_rules_service import run_complete_image_workflow, IMAGE_TYPES

# Test data with English product name
product_info = {
    'product_name_en': 'Portable USB Juicer Cup',
    'product_category': 'Kitchen',
    'product_color': 'white',
    'core_selling_points': ['Portable', 'Large Capacity', 'Easy Clean', 'USB Charging', 'Outdoor Use'],
    'usage_scenarios': ['Outdoor', 'Office', 'Travel'],
    'material_craft': '304 Stainless Steel Blade',
    'product_dimensions': '20cm x 8cm',
}

result = run_complete_image_workflow(product_info)

if result['success']:
    print('=' * 60)
    print('Image Workflow Test - SUCCESS')
    print('=' * 60)
    print(f"Total images: {result['data']['summary']['total_images']}")
    print(f"Image types: {result['data']['summary']['image_types']}")
    print(f"Estimated cost: {result['data']['summary']['estimated_cost_cny']} CNY")
    print()
    
    print('Image Plan:')
    for image_type, type_data in result['data']['plan']['image_types'].items():
        type_name = IMAGE_TYPES[image_type]['name']
        print(f"  {type_name}: {type_data['count']} images")
    
    print()
    print('First 5 tasks (checking for English only):')
    for task in result['data']['tasks'][:5]:
        print(f"  [{task['id']}] {task['image_type_name']}")
        print(f"  Prompt: {task['prompt'][:100]}...")
        print(f"  Filename: {task['filename']}")
        
        # Check for Chinese characters in prompt
        if re.search(r'[\u4e00-\u9fff]', task['prompt']):
            print(f"  WARNING: Chinese characters found in prompt!")
        else:
            print(f"  Status: English only [OK]")
        print()
else:
    print(f"FAILED: {result['error']}")
