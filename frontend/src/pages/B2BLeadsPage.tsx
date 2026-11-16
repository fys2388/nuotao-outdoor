/**
 * B2B 线索管理页（M2.5.2）
 *
 * 在现有 AI OS console 内管理公开展示站收到的询盘线索（b2b_leads）。
 * 复用现有受保护 admin API（/api/v1/admin/b2b/leads）与 RBAC/workspace 模型。
 * 不新建独立 admin 系统，不通过公开路由暴露内部线索详情。
 * Spec: reports/b2b/CHATGPT_M25_SPEC.md (M2.5.2)
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Card, Table, Button, Drawer, Input, Select, Tag, Space, Typography,
  Descriptions, Form, Modal, Badge, message,
} from 'antd';
import { ReloadOutlined, CheckOutlined, UserOutlined } from '@ant-design/icons';
import { api } from '../api/client';

const { Title, Text } = Typography;

// 与后端 B2B_LEAD_STATUSES 对齐（M2.5.1 终态拆分）。
const STATUS_OPTIONS = [
  { value: 'new', label: 'New', color: 'blue' },
  { value: 'reviewing', label: 'Reviewing', color: 'cyan' },
  { value: 'qualified', label: 'Qualified', color: 'green' },
  { value: 'contacted', label: 'Contacted', color: 'purple' },
  { value: 'converted', label: 'Converted', color: 'gold' },
  { value: 'closed_lost', label: 'Closed lost', color: 'red' },
  { value: 'spam', label: 'Spam', color: 'default' },
];

const statusColor = (s: string) =>
  STATUS_OPTIONS.find((o) => o.value === s)?.color ?? 'default';
const statusLabel = (s: string) =>
  STATUS_OPTIONS.find((o) => o.value === s)?.label ?? s;

interface Lead {
  id: string;
  reference_number: string;
  company_name: string;
  contact_name: string;
  email: string;
  country: string;
  business_type: string;
  products_of_interest: string[] | null;
  message: string;
  status: string;
  assigned_to: string | null;
  internal_notes: string | null;
  created_at: string;
  converted_application_id: string | null;
}

interface ListResponse<T> {
  items: T[];
  total: number;
}

const B2BLeadsPage: React.FC = () => {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [assignedFilter, setAssignedFilter] = useState<string | undefined>();
  const [selected, setSelected] = useState<Lead | null>(null);
  const [actionForm] = Form.useForm();
  const [convertTarget, setConvertTarget] = useState<Lead | null>(null);
  const [convertAgentId, setConvertAgentId] = useState('');

  const fetchLeads = useCallback(async () => {
    setLoading(true);
    try {
      const resp = (await api.getB2BLeads({
        status: statusFilter,
        assigned_to: assignedFilter,
        page,
        page_size: 20,
      })) as ListResponse<Lead>;
      setLeads(resp.items ?? []);
      setTotal(resp.total ?? 0);
    } catch (e) {
      message.error('Failed to load leads');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, assignedFilter, page]);

  useEffect(() => {
    fetchLeads();
  }, [fetchLeads]);

  const openDetail = (lead: Lead) => {
    setSelected(lead);
    actionForm.resetFields();
  };

  const applyAction = async (values: Record<string, unknown>) => {
    if (!selected) return;
    try {
      await api.updateB2BLead(selected.id, values);
      message.success('Lead updated');
      setSelected(null);
      fetchLeads();
    } catch (e) {
      message.error('Update failed (invalid transition or missing reason?)');
    }
  };

  const openConvert = (lead: Lead) => {
    setConvertAgentId('');
    setConvertTarget(lead);
  };

  const doConvert = async () => {
    if (!convertTarget || !convertAgentId.trim()) return;
    try {
      await api.convertB2BLead(convertTarget.id, convertAgentId.trim());
      message.success('Lead converted');
      setConvertTarget(null);
      fetchLeads();
    } catch (e) {
      message.error('Conversion failed (only qualified/contacted, must link a real agent)');
    }
  };

  const columns = useMemo(
    () => [
      { title: 'Reference', dataIndex: 'reference_number', key: 'ref', width: 160 },
      { title: 'Company', dataIndex: 'company_name', key: 'company' },
      { title: 'Contact', dataIndex: 'contact_name', key: 'contact' },
      { title: 'Country', dataIndex: 'country', key: 'country', width: 110 },
      { title: 'Business type', dataIndex: 'business_type', key: 'biz', width: 130 },
      {
        title: 'Status',
        dataIndex: 'status',
        key: 'status',
        width: 130,
        render: (s: string) => <Tag color={statusColor(s)}>{statusLabel(s)}</Tag>,
      },
      { title: 'Owner', dataIndex: 'assigned_to', key: 'owner', width: 140,
        render: (v: string | null) => v || <Text type="secondary">—</Text> },
      {
        title: 'Created',
        dataIndex: 'created_at',
        key: 'created',
        width: 120,
        render: (v: string) => (v ? new Date(v).toLocaleDateString() : '—'),
      },
      {
        title: 'Actions',
        key: 'actions',
        width: 120,
        render: (_: unknown, record: Lead) => (
          <Space>
            <Button size="small" onClick={() => openDetail(record)}>Detail</Button>
            {(record.status === 'qualified' || record.status === 'contacted') && (
              <Button size="small" type="primary" ghost onClick={() => openConvert(record)}>
                Convert
              </Button>
            )}
          </Space>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [leads],
  );

  return (
    <Card>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Title level={4}>B2B Leads (public enquiries)</Title>
        <Space wrap>
          <Select
            allowClear
            placeholder="Status"
            style={{ width: 160 }}
            options={STATUS_OPTIONS}
            value={statusFilter}
            onChange={(v) => { setStatusFilter(v); setPage(1); }}
          />
          <Input
            allowClear
            placeholder="Assigned owner"
            style={{ width: 180 }}
            prefix={<UserOutlined />}
            value={assignedFilter}
            onChange={(e) => { setAssignedFilter(e.target.value || undefined); setPage(1); }}
          />
          <Button icon={<ReloadOutlined />} onClick={fetchLeads}>Refresh</Button>
        </Space>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={leads}
          loading={loading}
          pagination={{
            current: page,
            pageSize: 20,
            total,
            onChange: (p) => setPage(p),
            showTotal: (t) => `${t} leads`,
          }}
        />
      </Space>

      <Drawer
        title={selected ? `${selected.reference_number} — ${selected.company_name}` : ''}
        open={!!selected}
        onClose={() => setSelected(null)}
        width={520}
      >
        {selected && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="Status">
                <Badge color={statusColor(selected.status)} text={statusLabel(selected.status)} />
              </Descriptions.Item>
              <Descriptions.Item label="Contact">{selected.contact_name}</Descriptions.Item>
              <Descriptions.Item label="Email">{selected.email}</Descriptions.Item>
              <Descriptions.Item label="Country">{selected.country}</Descriptions.Item>
              <Descriptions.Item label="Business type">{selected.business_type}</Descriptions.Item>
              <Descriptions.Item label="Products of interest">
                {(selected.products_of_interest || []).join(', ') || '—'}
              </Descriptions.Item>
              <Descriptions.Item label="Owner">{selected.assigned_to || '—'}</Descriptions.Item>
              <Descriptions.Item label="Enquiry message">{selected.message}</Descriptions.Item>
              <Descriptions.Item label="Internal notes">{selected.internal_notes || '—'}</Descriptions.Item>
            </Descriptions>

            <Card size="small" title="Update lead (authorized operators only)">
              <Form layout="vertical" form={actionForm} onFinish={applyAction}>
                <Form.Item name="status" label="Change status">
                  <Select allowClear placeholder="New status" options={STATUS_OPTIONS} />
                </Form.Item>
                <Form.Item
                  name="internal_notes"
                  label="Internal note / reason"
                  tooltip="Required as the documented reason when marking closed_lost or spam"
                >
                  <Input.TextArea rows={3} placeholder="Reason (required for closed_lost / spam)" />
                </Form.Item>
                <Form.Item name="assigned_to" label="Assign owner">
                  <Input placeholder="owner@nuotaooutdoor.com" />
                </Form.Item>
                <Form.Item name="follow_up" label="Schedule follow-up (note)">
                  <Input placeholder="Follow-up note" />
                </Form.Item>
                <Button type="primary" htmlType="submit" icon={<CheckOutlined />}>
                  Apply update
                </Button>
              </Form>
            </Card>
          </Space>
        )}
      </Drawer>

      <Modal
        title="Convert lead to partner application"
        open={!!convertTarget}
        onOk={doConvert}
        onCancel={() => setConvertTarget(null)}
        okText="Convert"
        okButtonProps={{ disabled: !convertAgentId.trim() }}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text>
            Link qualified lead <b>{convertTarget?.reference_number}</b> to an existing formal
            B2B partner application. Conversion is authorized-only and idempotent.
          </Text>
          <Input
            placeholder="Target B2B agent (application) ID"
            value={convertAgentId}
            onChange={(e) => setConvertAgentId(e.target.value)}
          />
        </Space>
      </Modal>
    </Card>
  );
};

export default B2BLeadsPage;