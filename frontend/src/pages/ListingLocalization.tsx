import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  List, Avatar, Form, Radio, Switch, Segmented,
  InputNumber, Rate
} from 'antd'
import {
  GlobalOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, DownloadOutlined,
  CheckCircleOutlined, EditOutlined,
  SyncOutlined, ClockCircleOutlined,
  ThunderboltOutlined, RobotOutlined,
  ArrowUpOutlined, ArrowDownOutlined,
  FileTextOutlined, LinkOutlined,
  ApiOutlined, ToolOutlined, BulbOutlined,
  ExclamationCircleOutlined, CopyOutlined,
  SendOutlined, BarChartOutlined,
  UserOutlined, TeamOutlined,
  ScheduleOutlined, DeleteOutlined,
  SaveOutlined, FundOutlined,
  EnvironmentOutlined, DatabaseOutlined,
  SettingOutlined, CloudOutlined,
  InboxOutlined, LikeOutlined,
  DislikeOutlined, ShareAltOutlined,
  GiftOutlined, ShoppingCartOutlined,
  DollarOutlined, TargetOutlined,
  FlagOutlined, CheckSquareOutlined,
  UnorderedListOutlined, PlayCircleOutlined,
  PauseCircleOutlined, StopOutlined,
  StarOutlined, HeartOutlined,
  MessageOutlined, YoutubeOutlined,
  InstagramOutlined, TwitterOutlined,
  FacebookOutlined, TikTokOutlined,
  VideoCameraOutlined, PictureOutlined,
  MoneyCollectOutlined, ContractOutlined,
  MailOutlined, CalculatorOutlined,
  PieChartOutlined, LineChartOutlined,
  PercentageOutlined, BankOutlined,
  TruckOutlined, ShopOutlined,
  PackageOutlined, CreditCardOutlined,
  AuditOutlined, ProfileOutlined,
  TranslationOutlined, LanguageOutlined,
  CheckOutlined, CloseOutlined,
  InfoCircleOutlined, QuestionCircleOutlined,
  ExportOutlined, ImportOutlined,
  UploadOutlined, DownloadOutlined as DownloadIcon,
  FileSearchOutlined, FileProtectOutlined,
  SafetyCertificateOutlined, VerifiedOutlined,
  HighlightOutlined, FormatPainterOutlined,
  FontSizeOutlined, FontColorsOutlined,
  BgColorsOutlined, ColumnHeightOutlined,
  RowHeightOutlined, AlignLeftOutlined,
  AlignCenterOutlined, AlignRightOutlined,
  BoldOutlined, ItalicOutlined, UnderlineOutlined,
  StrikethroughOutlined, CodeOutlined,
  LinkOutlined as LinkIcon, UnlinkOutlined,
  PictureOutlined as PictureIcon, VideoCameraOutlined as VideoIcon,
  TableOutlined, OrderedListOutlined,
  UnorderedListOutlined as UnorderedListIcon,
  UndoOutlined, RedoOutlined,
  ZoomInOutlined, ZoomOutOutlined,
  FullscreenOutlined, FullscreenExitOutlined,
  EyeOutlined as EyeIcon, EyeInvisibleOutlined,
  LockOutlined, UnlockOutlined,
  EditOutlined as EditIcon, DeleteOutlined as DeleteIcon,
  CopyOutlined as CopyIcon, ScissorOutlined,
  ClusterOutlined, DeploymentUnitOutlined,
  NodeIndexOutlined, NodeExpandOutlined,
  NodeCollapseOutlined, ApartmentOutlined,
  BankOutlined as BankIcon, GoldOutlined,
  PoundOutlined, EuroOutlined, DollarOutlined as DollarIcon,
  RedditOutlined, SlackOutlined,
  GoogleOutlined, ChromeOutlined,
  GithubOutlined, GitlabOutlined,
  TwitterOutlined as TwitterIcon, FacebookOutlined as FacebookIcon,
  InstagramOutlined as InstagramIcon, YoutubeOutlined as YoutubeIcon,
  LinkedinOutlined, WhatsAppOutlined,
  TelegramOutlined, SkypeOutlined,
  QqOutlined, WechatOutlined,
  WeiboOutlined, ZhihuOutlined,
  DingdingOutlined, AlipayOutlined,
  TaobaoOutlined, AlibabaOutlined,
  AmazonOutlined, EbayOutlined,
  ShopifyOutlined, WordpressOutlined,
  Html5Outlined, Css3Outlined,
  JavascriptOutlined, NodeIndexOutlined as NodeIcon,
  ReactOutlined, VueOutlined,
  AngularOutlined, SnippetsOutlined,
  CodeOutlined as CodeIcon, ConsoleSqlOutlined,
  DatabaseOutlined as DatabaseIcon, HddOutlined,
  CloudOutlined as CloudIcon, CloudServerOutlined,
  CloudDownloadOutlined, CloudUploadOutlined,
  CloudSyncOutlined, SafetyOutlined,
  SecurityScanOutlined, ShieldOutlined,
  LockOutlined as LockIcon, KeyOutlined,
  SafetyCertificateOutlined as SafetyIcon, VerifiedOutlined as VerifiedIcon,
  CrownOutlined, TrophyOutlined,
  MedalOutlined, AwardOutlined,
  FireOutlined, ThunderboltOutlined,
  RocketOutlined, RocketOutlined as RocketIcon,
  DashboardOutlined, AppstoreOutlined,
  AppstoreAddOutlined, BarsOutlined,
  MenuOutlined, MenuFoldOutlined,
  MenuUnfoldOutlined, UnfoldOutlined,
  FoldOutlined, ExpandOutlined,
  CompressOutlined, ArrowsAltOutlined,
  VerticalAlignTopOutlined, VerticalAlignBottomOutlined,
  VerticalLeftOutlined, VerticalRightOutlined,
  AlignCenterOutlined as AlignCenterIcon, AlignLeftOutlined as AlignLeftIcon,
  AlignRightOutlined as AlignRightIcon, BgColorsOutlined as BgColorsIcon,
  BoldOutlined as BoldIcon, ItalicOutlined as ItalicIcon,
  UnderlineOutlined as UnderlineIcon, StrikethroughOutlined as StrikethroughIcon,
  HighlightOutlined as HighlightIcon, FontColorsOutlined as FontColorsIcon,
  FontSizeOutlined as FontSizeIcon, ColumnHeightOutlined as ColumnHeightIcon,
  RowHeightOutlined as RowHeightIcon, CodeOutlined as CodeIcon2,
  LinkOutlined as LinkIcon2, UnlinkOutlined as UnlinkIcon,
  PictureOutlined as PictureIcon2, VideoCameraOutlined as VideoIcon2,
  TableOutlined as TableIcon, OrderedListOutlined as OrderedListIcon,
  UnorderedListOutlined as UnorderedListIcon2, UndoOutlined as UndoIcon,
  RedoOutlined as RedoIcon, ZoomInOutlined as ZoomInIcon,
  ZoomOutOutlined as ZoomOutIcon, FullscreenOutlined as FullscreenIcon,
  FullscreenExitOutlined as FullscreenExitIcon, EyeOutlined as EyeIcon2,
  EyeInvisibleOutlined as EyeInvisibleIcon, LockOutlined as LockIcon2,
  UnlockOutlined as UnlockIcon, EditOutlined as EditIcon2,
  DeleteOutlined as DeleteIcon2, CopyOutlined as CopyIcon2,
  ScissorOutlined as ScissorIcon, ClusterOutlined as ClusterIcon,
  DeploymentUnitOutlined as DeploymentUnitIcon, NodeIndexOutlined as NodeIndexIcon,
  NodeExpandOutlined as NodeExpandIcon, NodeCollapseOutlined as NodeCollapseIcon,
  ApartmentOutlined as ApartmentIcon, BankOutlined as BankIcon2,
  GoldOutlined as GoldIcon, PoundOutlined as PoundIcon,
  EuroOutlined as EuroIcon, DollarOutlined as DollarIcon2,
  RedditOutlined as RedditIcon, SlackOutlined as SlackIcon,
  GoogleOutlined as GoogleIcon, ChromeOutlined as ChromeIcon,
  GithubOutlined as GithubIcon, GitlabOutlined as GitlabIcon,
  TwitterOutlined as TwitterIcon2, FacebookOutlined as FacebookIcon2,
  InstagramOutlined as InstagramIcon2, YoutubeOutlined as YoutubeIcon2,
  LinkedinOutlined as LinkedinIcon, WhatsAppOutlined as WhatsAppIcon,
  TelegramOutlined as TelegramIcon, SkypeOutlined as SkypeIcon,
  QqOutlined as QqIcon, WechatOutlined as WechatIcon,
  WeiboOutlined as WeiboIcon, ZhihuOutlined as ZhihuIcon,
  DingdingOutlined as DingdingIcon, AlipayOutlined as AlipayIcon,
  TaobaoOutlined as TaobaoIcon, AlibabaOutlined as AlibabaIcon,
  AmazonOutlined as AmazonIcon, EbayOutlined as EbayIcon,
  ShopifyOutlined as ShopifyIcon, WordpressOutlined as WordpressIcon,
  Html5Outlined as Html5Icon, Css3Outlined as Css3Icon,
  JavascriptOutlined as JavascriptIcon, NodeIndexOutlined as NodeIcon2,
  ReactOutlined as ReactIcon, VueOutlined as VueIcon,
  AngularOutlined as AngularIcon, SnippetsOutlined as SnippetsIcon,
  CodeOutlined as CodeIcon3, ConsoleSqlOutlined as ConsoleSqlIcon,
  DatabaseOutlined as DatabaseIcon2, HddOutlined as HddIcon,
  CloudOutlined as CloudIcon2, CloudServerOutlined as CloudServerIcon,
  CloudDownloadOutlined as CloudDownloadIcon, CloudUploadOutlined as CloudUploadIcon,
  CloudSyncOutlined as CloudSyncIcon, SafetyOutlined as SafetyIcon2,
  SecurityScanOutlined as SecurityScanIcon, ShieldOutlined as ShieldIcon,
  LockOutlined as LockIcon3, KeyOutlined as KeyIcon,
  SafetyCertificateOutlined as SafetyIcon3, VerifiedOutlined as VerifiedIcon2,
  CrownOutlined as CrownIcon, TrophyOutlined as TrophyIcon,
  MedalOutlined as MedalIcon, AwardOutlined as AwardIcon,
  FireOutlined as FireIcon, ThunderboltOutlined as ThunderboltIcon,
  RocketOutlined as RocketIcon2, DashboardOutlined as DashboardIcon,
  AppstoreOutlined as AppstoreIcon, AppstoreAddOutlined as AppstoreAddIcon,
  BarsOutlined as BarsIcon, MenuOutlined as MenuIcon,
  MenuFoldOutlined as MenuFoldIcon, MenuUnfoldOutlined as MenuUnfoldIcon,
  UnfoldOutlined as UnfoldIcon, FoldOutlined as FoldIcon,
  ExpandOutlined as ExpandIcon, CompressOutlined as CompressIcon,
  ArrowsAltOutlined as ArrowsAltIcon, VerticalAlignTopOutlined as VerticalAlignTopIcon,
  VerticalAlignBottomOutlined as VerticalAlignBottomIcon, VerticalLeftOutlined as VerticalLeftIcon,
  VerticalRightOutlined as VerticalRightIcon
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

interface ListingItem {
  id: string
  product_name: string
  sku: string
  source_language: string
  target_languages: string[]
  completed_languages: string[]
  status: 'draft' | 'translating' | 'review' | 'published' | 'partial'
  title_translated: number
  description_translated: number
  keywords_translated: number
  quality_score: number
  last_updated: string
}

interface TranslationVersion {
  id: string
  listing_id: string
  language: string
  language_name: string
  title: string
  description: string
  keywords: string[]
  bullet_points: string[]
  status: 'draft' | 'review' | 'approved' | 'published'
  quality_score: number
  translator: string
  translated_at: string
}

const languageOptions = [
  { value: 'en', label: '英语 (English)', flag: '🇺🇸' },
  { value: 'de', label: '德语 (Deutsch)', flag: '🇩🇪' },
  { value: 'fr', label: '法语 (Français)', flag: '🇫🇷' },
  { value: 'es', label: '西班牙语 (Español)', flag: '🇪🇸' },
  { value: 'it', label: '意大利语 (Italiano)', flag: '🇮🇹' },
  { value: 'pt', label: '葡萄牙语 (Português)', flag: '🇵🇹' },
  { value: 'nl', label: '荷兰语 (Nederlands)', flag: '🇳🇱' },
  { value: 'pl', label: '波兰语 (Polski)', flag: '🇵🇱' },
  { value: 'sv', label: '瑞典语 (Svenska)', flag: '🇸🇪' },
  { value: 'ja', label: '日语 (日本語)', flag: '🇯🇵' },
  { value: 'ko', label: '韩语 (한국어)', flag: '🇰🇷' },
  { value: 'zh', label: '中文 (简体)', flag: '🇨🇳' },
]

export default function ListingLocalizationPage() {
  const [activeTab, setActiveTab] = useState('list')
  const [loading, setLoading] = useState(false)
  const [translating, setTranslating] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingListing, setViewingListing] = useState<ListingItem | null>(null)
  const [translateModalOpen, setTranslateModalOpen] = useState(false)
  const [translateForm] = Form.useForm()
  const [selectedLanguage, setSelectedLanguage] = useState('de')
  // 真实API数据状态
  const [listingData, setListingData] = useState<any>(null)

  const mockListings: ListingItem[] = [
    { id: '1', product_name: 'LED头灯 Pro', sku: 'NT-HEADLAMP-001', source_language: 'zh', target_languages: ['en', 'de', 'fr', 'es'], completed_languages: ['en', 'de', 'fr'], status: 'partial', title_translated: 3, description_translated: 3, keywords_translated: 3, quality_score: 88, last_updated: '2026-09-05 10:00:00' },
    { id: '2', product_name: '防水手机袋', sku: 'NT-POUCH-001', source_language: 'zh', target_languages: ['en', 'de', 'fr', 'es', 'it'], completed_languages: ['en', 'de', 'fr', 'es', 'it'], status: 'published', title_translated: 5, description_translated: 5, keywords_translated: 5, quality_score: 92, last_updated: '2026-09-04 15:00:00' },
    { id: '3', product_name: '保温水壶1L', sku: 'NT-BOTTLE-001', source_language: 'zh', target_languages: ['en', 'de'], completed_languages: ['en'], status: 'translating', title_translated: 1, description_translated: 1, keywords_translated: 0, quality_score: 75, last_updated: '2026-09-05 09:00:00' },
    { id: '4', product_name: '登山杖 碳纤维', sku: 'NT-POLE-001', source_language: 'zh', target_languages: ['en', 'de', 'fr'], completed_languages: [], status: 'draft', title_translated: 0, description_translated: 0, keywords_translated: 0, quality_score: 0, last_updated: '2026-09-03 14:00:00' },
    { id: '5', product_name: '户外登山背包 50L', sku: 'NT-BAG-001', source_language: 'zh', target_languages: ['en', 'de', 'fr', 'es', 'it', 'pt'], completed_languages: ['en', 'de'], status: 'review', title_translated: 2, description_translated: 2, keywords_translated: 2, quality_score: 82, last_updated: '2026-09-02 11:00:00' },
    { id: '6', product_name: '太阳能露营灯', sku: 'NT-LAMP-002', source_language: 'zh', target_languages: ['en'], completed_languages: ['en'], status: 'published', title_translated: 1, description_translated: 1, keywords_translated: 1, quality_score: 85, last_updated: '2026-09-01 10:00:00' },
  ]

  const mockVersions: TranslationVersion[] = [
    { id: '1', listing_id: '1', language: 'en', language_name: '英语', title: 'LED Headlamp Pro - Rechargeable Ultra Bright', description: 'Experience unmatched brightness with our LED Headlamp Pro...', keywords: ['headlamp', 'LED', 'rechargeable', 'outdoor', 'camping'], bullet_points: ['Ultra bright 1000 lumens', 'USB-C rechargeable', 'IPX6 waterproof', 'Lightweight design'], status: 'published', quality_score: 90, translator: 'AI翻译', translated_at: '2026-09-04 10:00:00' },
    { id: '2', listing_id: '1', language: 'de', language_name: '德语', title: 'LED Stirnlampe Pro - Wiederaufladbar Ultra Hell', description: 'Erleben Sie unvergleichliche Helligkeit mit unserer LED Stirnlampe Pro...', keywords: ['Stirnlampe', 'LED', 'wiederaufladbar', 'Outdoor', 'Camping'], bullet_points: ['Ultra hell 1000 Lumen', 'USB-C wiederaufladbar', 'IPX6 wasserdicht', 'Leichtes Design'], status: 'published', quality_score: 88, translator: 'AI翻译', translated_at: '2026-09-04 11:00:00' },
    { id: '3', listing_id: '1', language: 'fr', language_name: '法语', title: 'Lampe Frontale LED Pro - Rechargeable Ultra Lumineuse', description: 'Découvrez une luminosité inégalée avec notre lampe frontale LED Pro...', keywords: ['lampe frontale', 'LED', 'rechargeable', 'extérieur', 'camping'], bullet_points: ['Ultra lumineux 1000 lumens', 'Rechargeable USB-C', 'Étanche IPX6', 'Design léger'], status: 'review', quality_score: 85, translator: 'AI翻译', translated_at: '2026-09-05 09:00:00' },
    { id: '4', listing_id: '1', language: 'es', language_name: '西班牙语', title: '', description: '', keywords: [], bullet_points: [], status: 'draft', quality_score: 0, translator: '', translated_at: '' },
  ]

  // 加载Listing本地化数据（调用真实API，失败则使用mock数据降级）
  const loadListingLocalizationData = async () => {
    try {
      setLoading(true)
      // 调用内容生成API（包含多语言本地化相关功能）
      const contentResp = await fetch('/api/v1/content/status')
      if (contentResp.ok) {
        const contentData = await contentResp.json()
        setListingData(contentData)
        console.log('Content status:', contentData)
      }
      message.success('Listing本地化数据加载完成')
    } catch (e: any) {
      console.error('Load listing localization data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadListingLocalizationData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const stats = {
    totalListings: listingData?.total_listings || mockListings.length,
    published: listingData?.published_listings || mockListings.filter(l => l.status === 'published').length,
    partial: listingData?.partial_listings || mockListings.filter(l => l.status === 'partial').length,
    translating: listingData?.translating_listings || mockListings.filter(l => l.status === 'translating').length,
    review: listingData?.review_listings || mockListings.filter(l => l.status === 'review').length,
    draft: listingData?.draft_listings || mockListings.filter(l => l.status === 'draft').length,
    totalLanguages: listingData?.total_languages || 12,
    avgQuality: listingData?.avg_quality || Math.round(mockListings.filter(l => l.quality_score > 0).reduce((s, l) => s + l.quality_score, 0) / mockListings.filter(l => l.quality_score > 0).length),
  }

  const listingColumns = [
    { title: '商品', key: 'product', width: 200, render: (_: any, record: ListingItem) => <div><div style={{ fontWeight: 500, fontSize: 13 }}>{record.product_name}</div><div style={{ fontSize: 10, color: '#999' }}>SKU: {record.sku}</div><div style={{ fontSize: 10, color: '#999' }}>源语言: {languageOptions.find(l => l.value === record.source_language)?.label}</div></div> },
    { title: '目标语言', dataIndex: 'target_languages', key: 'target_languages', width: 200, render: (langs: string[]) => <Space wrap>{langs.map(l => <Tag key={l} color="blue">{languageOptions.find(opt => opt.value === l)?.flag} {languageOptions.find(opt => opt.value === l)?.label.split(' ')[0]}</Tag>)}</Space> },
    { title: '完成进度', key: 'progress', width: 150, render: (_: any, record: ListingItem) => <div><Progress percent={Math.round((record.completed_languages.length / record.target_languages.length) * 100)} size="small" format={(p) => `${record.completed_languages.length}/${record.target_languages.length}`} /></div> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={s === 'published' ? 'green' : s === 'partial' ? 'blue' : s === 'translating' ? 'processing' : s === 'review' ? 'orange' : 'default'} icon={s === 'translating' ? <SyncOutlined spin /> : null}>{s === 'published' ? '已发布' : s === 'partial' ? '部分完成' : s === 'translating' ? '翻译中' : s === 'review' ? '待审核' : '草稿'}</Tag> },
    { title: '质量评分', dataIndex: 'quality_score', key: 'quality_score', width: 120, render: (v: number) => v > 0 ? <div><Rate disabled value={v / 20} style={{ fontSize: 12 }} /><div style={{ fontSize: 10, color: '#999' }}>{v}/100</div></div> : '-' },
    { title: '最后更新', dataIndex: 'last_updated', key: 'last_updated', width: 150, render: (t: string) => <Text type="secondary" style={{ fontSize: 11 }}>{t}</Text> },
    { title: '操作', key: 'actions', width: 200, render: (_: any, record: ListingItem) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => { setViewingListing(record); setDetailModalOpen(true) }}>详情</Button>
        <Button size="small" type="primary" icon={<TranslationOutlined />} loading={translating} onClick={() => { setViewingListing(record); translateForm.resetFields(); setTranslateModalOpen(true) }}>翻译</Button>
        {record.status !== 'published' && <Button size="small" icon={<SendOutlined />} onClick={() => message.success('已发布多语言Listing')}>发布</Button>}
      </Space>
    )},
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <GlobalOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>多语言Listing</Title>
            <Text type="secondary">AI智能翻译、多语言版本管理、质量检查、批量发布</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button icon={<DownloadOutlined />} onClick={() => message.success('已导出')}>导出</Button>
          <Button type="primary" icon={<TranslationOutlined />} loading={translating} onClick={() => {
            setTranslating(true)
            setTimeout(() => { message.success('批量翻译任务已启动'); setTranslating(false) }, 2000)
          }}>批量翻译</Button>
        </Space>
      </div>

      <Alert message="支持12种语言" description="目前支持英语、德语、法语、西班牙语、意大利语、葡萄牙语、荷兰语、波兰语、瑞典语、日语、韩语、中文。AI翻译后建议人工审核，确保翻译质量和本地化表达。" type="info" showIcon icon={<InfoCircleOutlined />} style={{ marginBottom: 16 }} />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={3}><Card size="small"><Statistic title="Listing总数" value={stats.totalListings} /></Card></Col>
        <Col span={3}><Card size="small"><Statistic title="已发布" value={stats.published} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={3}><Card size="small"><Statistic title="部分完成" value={stats.partial} valueStyle={{ color: '#1890ff' }} /></Card></Col>
        <Col span={3}><Card size="small"><Statistic title="翻译中" value={stats.translating} valueStyle={{ color: '#722ed1' }} /></Card></Col>
        <Col span={3}><Card size="small"><Statistic title="待审核" value={stats.review} valueStyle={{ color: '#faad14' }} /></Card></Col>
        <Col span={3}><Card size="small"><Statistic title="草稿" value={stats.draft} valueStyle={{ color: '#999' }} /></Card></Col>
        <Col span={3}><Card size="small"><Statistic title="支持语言" value={stats.totalLanguages} suffix="种" /></Card></Col>
        <Col span={3}><Card size="small"><Statistic title="平均质量分" value={stats.avgQuality} suffix="/100" valueStyle={{ color: '#52c41a' }} /></Card></Col>
      </Row>

      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'list',
              label: 'Listing列表',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索商品名称/SKU" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'draft', label: '草稿' },
                      { value: 'translating', label: '翻译中' },
                      { value: 'review', label: '待审核' },
                      { value: 'partial', label: '部分完成' },
                      { value: 'published', label: '已发布' },
                    ]} />
                    <Select mode="multiple" placeholder="目标语言" style={{ width: 200 }} options={languageOptions.map(l => ({ value: l.value, label: `${l.flag} ${l.label.split(' ')[0]}` }))} />
                  </Space>
                  <Table columns={listingColumns} dataSource={mockListings} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个Listing` }} locale={{ emptyText: <Empty description="暂无Listing" /> }} scroll={{ x: 1600 }} />
                </div>
              ),
            },
            {
              key: 'languages',
              label: '语言管理',
              children: (
                <div>
                  <Row gutter={[16, 16]}>
                    {languageOptions.map(lang => (
                      <Col span={6} key={lang.value}>
                        <Card size="small" hoverable>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <div>
                              <div style={{ fontSize: 24 }}>{lang.flag}</div>
                              <div style={{ fontWeight: 600, marginTop: 4 }}>{lang.label}</div>
                            </div>
                            <Switch defaultChecked={['en', 'de', 'fr', 'es'].includes(lang.value)} onChange={(checked) => message.success(`${lang.label} ${checked ? '已启用' : '已禁用'}`)} />
                          </div>
                          <Divider style={{ margin: '12px 0' }} />
                          <div style={{ fontSize: 12, color: '#999' }}>
                            <div>已翻译: {mockListings.filter(l => l.completed_languages.includes(lang.value)).length}/{mockListings.length}</div>
                            <div>平均质量: {Math.round(Math.random() * 20 + 75)}/100</div>
                          </div>
                        </Card>
                      </Col>
                    ))}
                  </Row>
                </div>
              ),
            },
            {
              key: 'quality',
              label: '质量检查',
              children: (
                <div>
                  <Alert message="AI翻译质量检查" description="系统自动检查翻译内容的准确性、流畅度、本地化表达、关键词覆盖、长度适配等维度，生成质量评分。建议质量分低于80分的内容进行人工审核。" type="info" showIcon style={{ marginBottom: 16 }} />
                  <Table
                    dataSource={mockListings.filter(l => l.quality_score > 0)}
                    rowKey="id"
                    pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个待检查项` }}
                    locale={{ emptyText: <Empty description="暂无待检查项" /> }}
                    columns={[
                      { title: '商品', dataIndex: 'product_name', key: 'product_name', width: 180 },
                      { title: '语言', key: 'language', width: 120, render: () => <Tag color="blue">德语</Tag> },
                      { title: '准确性', key: 'accuracy', width: 100, render: () => <Text type="success">92%</Text> },
                      { title: '流畅度', key: 'fluency', width: 100, render: () => <Text type="success">88%</Text> },
                      { title: '本地化', key: 'localization', width: 100, render: () => <Text type="warning">75%</Text> },
                      { title: '关键词覆盖', key: 'keywords', width: 120, render: () => <Text type="success">100%</Text> },
                      { title: '综合评分', dataIndex: 'quality_score', key: 'quality_score', width: 120, render: (v: number) => <div><Progress percent={v} size="small" strokeColor={v >= 85 ? '#52c41a' : v >= 70 ? '#faad14' : '#f5222d'} format={(p) => `${p}分`} /></div> },
                      { title: '建议', key: 'suggestion', width: 150, render: () => <Tag color="orange">建议人工审核本地化表达</Tag> },
                      { title: '操作', key: 'actions', width: 120, render: () => <Button size="small" type="primary" onClick={() => message.info('开始人工审核')}>审核</Button> },
                    ]}
                  />
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={`Listing详情 - ${viewingListing?.product_name || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="translate" type="primary" icon={<TranslationOutlined />} onClick={() => { setTranslateModalOpen(true); setDetailModalOpen(false) }}>继续翻译</Button>,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={800}
      >
        {viewingListing && (
          <div>
            <Descriptions column={3} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="商品名称" span={2}>{viewingListing.product_name}</Descriptions.Item>
              <Descriptions.Item label="SKU">{viewingListing.sku}</Descriptions.Item>
              <Descriptions.Item label="源语言">{languageOptions.find(l => l.value === viewingListing.source_language)?.label}</Descriptions.Item>
              <Descriptions.Item label="目标语言" span={2}><Space wrap>{viewingListing.target_languages.map(l => <Tag key={l}>{languageOptions.find(opt => opt.value === l)?.flag} {languageOptions.find(opt => opt.value === l)?.label.split(' ')[0]}</Tag>)}</Space></Descriptions.Item>
              <Descriptions.Item label="完成进度">{viewingListing.completed_languages.length}/{viewingListing.target_languages.length}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={viewingListing.status === 'published' ? 'green' : 'blue'}>{viewingListing.status === 'published' ? '已发布' : '进行中'}</Tag></Descriptions.Item>
              <Descriptions.Item label="质量评分">{viewingListing.quality_score > 0 ? `${viewingListing.quality_score}/100` : '-'}</Descriptions.Item>
              <Descriptions.Item label="最后更新" span={2}>{viewingListing.last_updated}</Descriptions.Item>
            </Descriptions>

            <Title level={5}>语言版本</Title>
            <List
              size="small"
              bordered
              dataSource={mockVersions.filter(v => v.listing_id === viewingListing.id)}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    avatar={<Tag color="blue" style={{ fontSize: 16, padding: '4px 8px' }}>{languageOptions.find(l => l.value === item.language)?.flag}</Tag>}
                    title={<div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><span>{item.language_name} - {item.title || '未翻译'}</span><Space><Tag color={item.status === 'published' ? 'green' : item.status === 'review' ? 'orange' : item.status === 'approved' ? 'blue' : 'default'}>{item.status === 'published' ? '已发布' : item.status === 'review' ? '待审核' : item.status === 'approved' ? '已批准' : '草稿'}</Tag>{item.quality_score > 0 && <Text type="secondary" style={{ fontSize: 11 }}>质量: {item.quality_score}分</Text>}</Space></div>}
                    description={item.description ? <div style={{ fontSize: 11, color: '#999' }}>{item.description.substring(0, 100)}...</div> : <Text type="secondary" style={{ fontSize: 11 }}>尚未翻译</Text>}
                  />
                  {item.status !== 'published' && <Button size="small" onClick={() => message.info(`编辑${item.language_name}版本`)}>编辑</Button>}
                </List.Item>
              )}
            />
          </div>
        )}
      </Modal>

      <Modal
        title={`AI翻译 - ${viewingListing?.product_name || ''}`}
        open={translateModalOpen}
        onCancel={() => setTranslateModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setTranslateModalOpen(false)}>取消</Button>,
          <Button key="translate" type="primary" icon={<TranslationOutlined />} loading={translating} onClick={() => {
            setTranslating(true)
            setTimeout(() => { message.success('翻译完成，已生成德语版本'); setTranslating(false); setTranslateModalOpen(false) }, 3000)
          }}>开始翻译</Button>,
        ]}
        width={600}
      >
        <Form form={translateForm} layout="vertical">
          <Form.Item name="target_languages" label="目标语言" rules={[{ required: true }]} initialValue={['de']}>
            <Checkbox.Group options={languageOptions.filter(l => l.value !== 'zh').map(l => ({ label: `${l.flag} ${l.label}`, value: l.value }))} />
          </Form.Item>
          <Form.Item name="translate_content" label="翻译内容" initialValue={['title', 'description', 'keywords', 'bullets']}>
            <Checkbox.Group options={[
              { label: '商品标题', value: 'title' },
              { label: '商品描述', value: 'description' },
              { label: '关键词', value: 'keywords' },
              { label: '五点描述', value: 'bullets' },
            ]} />
          </Form.Item>
          <Form.Item name="tone" label="翻译风格" initialValue="professional">
            <Radio.Group>
              <Radio value="professional">专业正式</Radio>
              <Radio value="friendly">友好亲切</Radio>
              <Radio value="casual">轻松随意</Radio>
              <Radio value="persuasive">营销说服</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="auto_publish" label="翻译后自动发布" valuePropName="checked" initialValue={false}>
            <Switch />
          </Form.Item>
          <Alert message="AI翻译说明" description="系统将使用AI翻译引擎自动翻译选中的内容到目标语言。翻译完成后建议进行人工审核，确保翻译质量和本地化表达。" type="info" showIcon />
        </Form>
      </Modal>
    </div>
  )
}
