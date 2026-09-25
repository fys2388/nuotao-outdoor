"""
Workflow Engine Test
"""
import asyncio
from app.services.workflow_engine import engine


async def test_workflow():
    """Test full workflow"""
    print("=" * 60)
    print("Workflow Engine Test")
    print("=" * 60)
    print()
    
    # 1. Create workflow instance
    print("1. Creating workflow instance...")
    instance = engine.create_instance(
        product_info={
            'name': 'LED Headlamp Pro',
            'category': 'Lighting',
            'price': '28.5',
            'source': '1688',
        },
        workflow_type='selection_to_wc',
        trigger_source='api_test',
    )
    print(f"   Instance ID: {instance['id']}")
    print(f"   Status: {instance['status']}")
    print(f"   Current node: {instance['current_node']}")
    print(f"   Nodes: {list(instance['nodes'].keys())}")
    print()
    
    # 2. Start instance
    print("2. Starting workflow instance...")
    instance = engine.start_instance(instance['id'])
    print(f"   Status: {instance['status']}")
    print(f"   Current node: {instance['current_node']}")
    print(f"   Selection node status: {instance['nodes']['selection']['status']}")
    print()
    
    # 3. Complete selection node
    print("3. Completing selection node...")
    instance = engine.complete_node(
        instance['id'],
        'selection',
        result={
            'success': True,
            'score': 85,
            'risk_level': 'low',
            'risk_tags': [],
            'recommendation': 'Strong recommendation',
        }
    )
    print(f"   Status: {instance['status']}")
    print(f"   Current node: {instance['current_node']}")
    print(f"   Editing node status: {instance['nodes']['editing']['status']}")
    print()
    
    # 4. Complete editing node
    print("4. Completing editing node...")
    instance = engine.complete_node(
        instance['id'],
        'editing',
        result={
            'success': True,
            'product_name': 'LED Headlamp Pro Rechargeable',
            'description': 'High brightness rechargeable LED headlamp...',
        }
    )
    print(f"   Status: {instance['status']}")
    print(f"   Current node: {instance['current_node']}")
    print(f"   Listing node status: {instance['nodes']['listing']['status']}")
    print()
    
    # 5. Complete listing node
    print("5. Completing listing node...")
    instance = engine.complete_node(
        instance['id'],
        'listing',
        result={
            'success': True,
            'woocommerce_id': 12345,
            'sku': 'NT-LED-09251200',
            'status': 'draft',
        }
    )
    print(f"   Status: {instance['status']}")
    print(f"   Current node: {instance['current_node']}")
    print(f"   Sync node status: {instance['nodes']['sync']['status']}")
    print()
    
    # 6. Complete sync node
    print("6. Completing sync node...")
    instance = engine.complete_node(
        instance['id'],
        'sync',
        result={
            'success': True,
            'synced': True,
            'woocommerce_id': 12345,
        }
    )
    print(f"   Status: {instance['status']}")
    print(f"   Current node: {instance['current_node']}")
    print()
    
    # 7. Print history
    print("7. Workflow history...")
    for h in instance['history']:
        print(f"   - {h['event']} at {h['timestamp']}")
    print()
    
    # 8. List instances
    print("8. Listing instances...")
    result = engine.list_instances(limit=10)
    print(f"   Total instances: {result['total']}")
    print()
    
    # 9. Test pause/resume
    print("9. Testing pause/resume...")
    instance2 = engine.create_instance(
        product_info={'name': 'Test Product 2', 'price': '50.0'},
        trigger_source='test',
    )
    engine.start_instance(instance2['id'])
    instance2 = engine.pause_instance(instance2['id'])
    print(f"   Paused status: {instance2['status']}")
    instance2 = engine.resume_instance(instance2['id'])
    print(f"   Resumed status: {instance2['status']}")
    print()
    
    # 10. Test node retry
    print("10. Testing node retry...")
    instance3 = engine.create_instance(
        product_info={'name': 'Test Product 3', 'price': '60.0'},
        trigger_source='test',
    )
    engine.start_instance(instance3['id'])
    
    # Fail the node
    instance3 = engine.fail_node(
        instance3['id'],
        'selection',
        error='API timeout'
    )
    print(f"   Failed status: {instance3['nodes']['selection']['status']}")
    
    # Retry
    instance3 = engine.retry_node(instance3['id'], 'selection')
    print(f"   Retry status: {instance3['nodes']['selection']['status']}")
    print(f"   Retry count: {instance3['nodes']['selection']['retry_count']}")
    print()
    
    print("=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(test_workflow())