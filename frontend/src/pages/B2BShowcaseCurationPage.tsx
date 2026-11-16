/**
 * B2B 商品展示审核页（M2.5.3）
 *
 * 受控 curation：控制哪些商品出现在公开无价格目录。
 * 默认关闭；未审核不公开；缺失证据告警；公开字段与内部采购数据隔离
 * （本页绝不显示/编辑价格、成本、利润、库存、供应商、内部 SKU）。
 * Spec: reports/b2b/CHATGPT_M25_SPEC.md (M2.5.3)
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Card, Table, Button, Input, Switch, Tag, Space, Typography, App as AntApp, message, Tooltip,
} from 'antd';
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { api } from '../api/client';

const { Title, Text } = Typography;

interface ShowcaseProduct {
  id: string;
  name: string;
  category: string | null;
  sku: string | null;
  b2b_showcase_enabled: boolean;
  b2b_public_slug: string | null;
  has_images: boolean;
  has_specifications: boolean;
  image_count: number;
  description_approved: boolean;
  specs_approved: boolean;
  missing_evidence: string[];
}

const B2BShowcaseCurationPage: React.FC = () => {
  const { modal } = AntApp.useApp();
  const [items, setItems] = useState<ShowcaseProduct[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const resp = (await api.getShowcaseProducts({ search: search || undefined })) as {
        items: ShowcaseProduct[];
      };
      setItems(resp.items ?? []);
    } catch (e) {
      message.error('Failed to load products');
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const update = async (product: ShowcaseProduct, patch: Record<string, unknown>) => {
    try {
      await api.updateShowcaseProduct(product.id, patch);
      message.success('Product showcase updated');
      fetchItems();
    } catch (e) {
      message.error('Update failed');
    }
  };

  const onToggleEnable = (product: ShowcaseProduct, enabled: boolean) => {
    if (enabled && product.missing_evidence.length > 0) {
      modal.warning({
        title: 'Missing required evidence',
        content: (
          <div>
            <p>
              This product is missing: <b>{product.missing_evidence.join(', ')}</b>.
            </p>
            <p>Complete public title/slug, an approved image, category, description and
              specifications before enabling the public showcase.</p>
          </div>
        ),
      });
      return;
    }
    update(product, { b2b_showcase_enabled: enabled });
  };

  const columns = [
    { title: 'Product', dataIndex: 'name', key: 'name' },
    { title: 'Category', dataIndex: 'category', key: 'category', width: 130,
      render: (v: string | null) => v || <Text type="secondary">—</Text> },
    {
      title: 'Evidence',
      key: 'evidence',
      width: 210,
      render: (_: unknown, r: ShowcaseProduct) => (
        <Space size={4} wrap>
          <Tag color={r.has_images ? 'green' : 'red'}>{r.image_count} img</Tag>
          <Tag color={r.has_specifications ? 'green' : 'red'}>specs</Tag>
          <Tag color={r.description_approved ? 'green' : 'orange'}>desc</Tag>
          {r.missing_evidence.length > 0 && (
            <Tooltip title={`Missing: ${r.missing_evidence.join(', ')}`}>
              <Tag color="red">{r.missing_evidence.length} missing</Tag>
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: 'Public slug',
      dataIndex: 'b2b_public_slug',
      key: 'slug',
      width: 200,
      render: (v: string | null, r: ShowcaseProduct) => (
        <Input.Search
          defaultValue={v || ''}
          placeholder="public-slug"
          enterButton="Save"
          onSearch={(val) => val.trim() && update(r, { b2b_public_slug: val.trim() })}
        />
      ),
    },
    {
      title: 'Showcase',
      key: 'enable',
      width: 110,
      render: (_: unknown, r: ShowcaseProduct) => (
        <Switch
          checked={r.b2b_showcase_enabled}
          onChange={(checked) => onToggleEnable(r, checked)}
        />
      ),
    },
  ];

  return (
    <Card>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Title level={4}>B2B Product Showcase Curation</Title>
        <Text type="secondary">
          Public no-price catalogue is opt-in per product. Default <b>disabled</b>. Enabling
          requires public title/slug, an approved image, category, description and specifications.
          Cost, pricing, inventory and supplier data are never exposed publicly.
        </Text>
        <Space wrap>
          <Input
            allowClear
            placeholder="Search products"
            style={{ width: 260 }}
            prefix={<SearchOutlined />}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Button icon={<ReloadOutlined />} onClick={fetchItems}>Refresh</Button>
        </Space>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={items}
          loading={loading}
          pagination={{ pageSize: 20, showTotal: (t) => `${t} products` }}
        />
      </Space>
    </Card>
  );
};

export default B2BShowcaseCurationPage;