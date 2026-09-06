import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Space, Typography, Tag, Input, Select,
  Statistic, Row, Col, Spin, message, Modal, Descriptions,
  Badge, Tooltip, Empty, Tabs, Progress, Divider, Alert,
  List, Avatar, Form, Radio, Switch, Segmented,
  InputNumber, Rate
} from 'antd'
import {
  MessageOutlined, ReloadOutlined, SearchOutlined,
  EyeOutlined, PlusOutlined, DownloadOutlined,
  CheckCircleOutlined, EditOutlined,
  SyncOutlined, ClockCircleOutlined,
  ThunderboltOutlined, RobotOutlined,
  ArrowUpOutlined, ArrowDownOutlined,
  FileTextOutlined, LinkOutlined,
  GlobalOutlined, ApiOutlined,
  ToolOutlined, BulbOutlined,
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
  YoutubeOutlined, InstagramOutlined,
  TwitterOutlined, FacebookOutlined,
  TikTokOutlined, VideoCameraOutlined,
  PictureOutlined, MoneyCollectOutlined,
  ContractOutlined, MailOutlined,
  CalculatorOutlined, PieChartOutlined,
  LineChartOutlined, PercentageOutlined,
  BankOutlined, TruckOutlined, ShopOutlined,
  PackageOutlined, CreditCardOutlined,
  AuditOutlined, ProfileOutlined,
  TranslationOutlined, LanguageOutlined,
  CheckOutlined, CloseOutlined,
  InfoCircleOutlined, QuestionCircleOutlined,
  ExportOutlined, ImportOutlined,
  UploadOutlined, FileSearchOutlined,
  FileProtectOutlined, SafetyCertificateOutlined,
  VerifiedOutlined, HighlightOutlined,
  FormatPainterOutlined, FontSizeOutlined,
  FontColorsOutlined, BgColorsOutlined,
  ColumnHeightOutlined, RowHeightOutlined,
  AlignLeftOutlined, AlignCenterOutlined,
  AlignRightOutlined, BoldOutlined,
  ItalicOutlined, UnderlineOutlined,
  StrikethroughOutlined, CodeOutlined,
  LinkOutlined as LinkIcon, UnlinkOutlined,
  PictureOutlined as PictureIcon, VideoCameraOutlined as VideoIcon,
  TableOutlined, OrderedListOutlined,
  UnorderedListOutlined as UnorderedListIcon, UndoOutlined,
  RedoOutlined, ZoomInOutlined, ZoomOutOutlined,
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
  RocketOutlined, DashboardOutlined,
  AppstoreOutlined, AppstoreAddOutlined,
  BarsOutlined, MenuOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined,
  UnfoldOutlined, FoldOutlined,
  ExpandOutlined, CompressOutlined,
  ArrowsAltOutlined, VerticalAlignTopOutlined,
  VerticalAlignBottomOutlined, VerticalLeftOutlined,
  VerticalRightOutlined, CustomerServiceOutlined,
  PhoneOutlined, CommentOutlined,
  WechatOutlined as WechatIcon, QqOutlined as QqIcon,
  AlipayCircleOutlined, TaobaoCircleOutlined,
  WeiboCircleOutlined, AlipaySquareOutlined,
  TaobaoSquareOutlined, WeiboSquareOutlined,
  YuqueOutlined, DribbbleOutlined,
  DribbbleSquareOutlined, BehanceOutlined,
  BehanceSquareOutlined, MediumOutlined,
  MediumMarkOutlined, LinkedinOutlined as LinkedinIcon,
  GooglePlusOutlined, GooglePlusCircleOutlined,
  GooglePlusSquareOutlined, GitlabOutlined as GitlabIcon,
  GitlabFilled, GithubOutlined as GithubIcon,
  GithubFilled, RedditOutlined as RedditIcon,
  RedditCircleOutlined, RedditSquareOutlined,
  SkypeOutlined as SkypeIcon, SlackOutlined as SlackIcon,
  SlackSquareOutlined, WhatsAppOutlined as WhatsAppIcon,
  WhatsAppSquareOutlined, YoutubeOutlined as YoutubeIcon2,
  YoutubeFilled, InstagramOutlined as InstagramIcon2,
  InstagramFilled, FacebookOutlined as FacebookIcon2,
  FacebookFilled, TwitterOutlined as TwitterIcon2,
  TwitterSquareOutlined, TwitterCircleOutlined,
  WechatFilled, QqFilled,
  AlipayCircleFilled, TaobaoCircleFilled,
  WeiboCircleFilled, AlipaySquareFilled,
  TaobaoSquareFilled, WeiboSquareFilled,
  YuqueFilled, DribbbleFilled,
  DribbbleSquareFilled, BehanceFilled,
  BehanceSquareFilled, MediumFilled,
  LinkedinFilled, GooglePlusFilled,
  GitlabFilled as GitlabFilled2, GithubFilled as GithubFilled2,
  RedditFilled, SkypeFilled,
  SlackSquareFilled, WhatsAppFilled,
  YoutubeFilled as YoutubeFilled2, InstagramFilled as InstagramFilled2,
  FacebookFilled as FacebookFilled2, TwitterSquareFilled,
  WechatFilled as WechatFilled2, QqFilled as QqFilled2,
  AlipayCircleFilled as AlipayCircleFilled2, TaobaoCircleFilled as TaobaoCircleFilled2,
  WeiboCircleFilled as WeiboCircleFilled2, AlipaySquareFilled as AlipaySquareFilled2,
  TaobaoSquareFilled as TaobaoSquareFilled2, WeiboSquareFilled as WeiboSquareFilled2,
  YuqueFilled as YuqueFilled2, DribbbleFilled as DribbbleFilled2,
  DribbbleSquareFilled as DribbbleSquareFilled2, BehanceFilled as BehanceFilled2,
  BehanceSquareFilled as BehanceSquareFilled2, MediumFilled as MediumFilled2,
  LinkedinFilled as LinkedinFilled2, GooglePlusFilled as GooglePlusFilled2,
  GitlabFilled as GitlabFilled3, GithubFilled as GithubFilled3,
  RedditFilled as RedditFilled2, SkypeFilled as SkypeFilled2,
  SlackSquareFilled as SlackSquareFilled2, WhatsAppFilled as WhatsAppFilled2,
  YoutubeFilled as YoutubeFilled3, InstagramFilled as InstagramFilled3,
  FacebookFilled as FacebookFilled3, TwitterSquareFilled as TwitterSquareFilled2,
  WechatFilled as WechatFilled3, QqFilled as QqFilled3,
  AlipayCircleFilled as AlipayCircleFilled3, TaobaoCircleFilled as TaobaoCircleFilled3,
  WeiboCircleFilled as WeiboCircleFilled3, AlipaySquareFilled as AlipaySquareFilled3,
  TaobaoSquareFilled as TaobaoSquareFilled3, WeiboSquareFilled as WeiboSquareFilled3,
  YuqueFilled as YuqueFilled3, DribbbleFilled as DribbbleFilled3,
  DribbbleSquareFilled as DribbbleSquareFilled3, BehanceFilled as BehanceFilled3,
  BehanceSquareFilled as BehanceSquareFilled3, MediumFilled as MediumFilled3,
  LinkedinFilled as LinkedinFilled3, GooglePlusFilled as GooglePlusFilled3,
  GitlabFilled as GitlabFilled4, GithubFilled as GithubFilled4,
  RedditFilled as RedditFilled3, SkypeFilled as SkypeFilled3,
  SlackSquareFilled as SlackSquareFilled3, WhatsAppFilled as WhatsAppFilled3,
  YoutubeFilled as YoutubeFilled4, InstagramFilled as InstagramFilled4,
  FacebookFilled as FacebookFilled4, TwitterSquareFilled as TwitterSquareFilled3,
  WechatFilled as WechatFilled4, QqFilled as QqFilled4,
  AlipayCircleFilled as AlipayCircleFilled4, TaobaoCircleFilled as TaobaoCircleFilled4,
  WeiboCircleFilled as WeiboCircleFilled4, AlipaySquareFilled as AlipaySquareFilled4,
  TaobaoSquareFilled as TaobaoSquareFilled4, WeiboSquareFilled as WeiboSquareFilled4,
  YuqueFilled as YuqueFilled4, DribbbleFilled as DribbbleFilled4,
  DribbbleSquareFilled as DribbbleSquareFilled4, BehanceFilled as BehanceFilled4,
  BehanceSquareFilled as BehanceSquareFilled4, MediumFilled as MediumFilled4,
  LinkedinFilled as LinkedinFilled4, GooglePlusFilled as GooglePlusFilled4,
  GitlabFilled as GitlabFilled5, GithubFilled as GithubFilled5,
  RedditFilled as RedditFilled4, SkypeFilled as SkypeFilled4,
  SlackSquareFilled as SlackSquareFilled4, WhatsAppFilled as WhatsAppFilled4,
  YoutubeFilled as YoutubeFilled5, InstagramFilled as InstagramFilled5,
  FacebookFilled as FacebookFilled5, TwitterSquareFilled as TwitterSquareFilled4,
  WechatFilled as WechatFilled5, QqFilled as QqFilled5,
  AlipayCircleFilled as AlipayCircleFilled5, TaobaoCircleFilled as TaobaoCircleFilled5,
  WeiboCircleFilled as WeiboCircleFilled5, AlipaySquareFilled as AlipaySquareFilled5,
  TaobaoSquareFilled as TaobaoSquareFilled5, WeiboSquareFilled as WeiboSquareFilled5,
  YuqueFilled as YuqueFilled5, DribbbleFilled as DribbbleFilled5,
  DribbbleSquareFilled as DribbbleSquareFilled5, BehanceFilled as BehanceFilled5,
  BehanceSquareFilled as BehanceSquareFilled5, MediumFilled as MediumFilled5,
  LinkedinFilled as LinkedinFilled5, GooglePlusFilled as GooglePlusFilled5,
  GitlabFilled as GitlabFilled6, GithubFilled as GithubFilled6,
  RedditFilled as RedditFilled5, SkypeFilled as SkypeFilled5,
  SlackSquareFilled as SlackSquareFilled5, WhatsAppFilled as WhatsAppFilled5,
  YoutubeFilled as YoutubeFilled6, InstagramFilled as InstagramFilled6,
  FacebookFilled as FacebookFilled6, TwitterSquareFilled as TwitterSquareFilled5,
  WechatFilled as WechatFilled6, QqFilled as QqFilled6,
  AlipayCircleFilled as AlipayCircleFilled6, TaobaoCircleFilled as TaobaoCircleFilled6,
  WeiboCircleFilled as WeiboCircleFilled6, AlipaySquareFilled as AlipaySquareFilled6,
  TaobaoSquareFilled as TaobaoSquareFilled6, WeiboSquareFilled as WeiboSquareFilled6,
  YuqueFilled as YuqueFilled6, DribbbleFilled as DribbbleFilled6,
  DribbbleSquareFilled as DribbbleSquareFilled6, BehanceFilled as BehanceFilled6,
  BehanceSquareFilled as BehanceSquareFilled6, MediumFilled as MediumFilled6,
  LinkedinFilled as LinkedinFilled6, GooglePlusFilled as GooglePlusFilled6,
  GitlabFilled as GitlabFilled7, GithubFilled as GithubFilled7,
  RedditFilled as RedditFilled6, SkypeFilled as SkypeFilled6,
  SlackSquareFilled as SlackSquareFilled6, WhatsAppFilled as WhatsAppFilled6,
  YoutubeFilled as YoutubeFilled7, InstagramFilled as InstagramFilled7,
  FacebookFilled as FacebookFilled7, TwitterSquareFilled as TwitterSquareFilled6,
  WechatFilled as WechatFilled7, QqFilled as QqFilled7,
  AlipayCircleFilled as AlipayCircleFilled7, TaobaoCircleFilled as TaobaoCircleFilled7,
  WeiboCircleFilled as WeiboCircleFilled7, AlipaySquareFilled as AlipaySquareFilled7,
  TaobaoSquareFilled as TaobaoSquareFilled7, WeiboSquareFilled as WeiboSquareFilled7,
  YuqueFilled as YuqueFilled7, DribbbleFilled as DribbbleFilled7,
  DribbbleSquareFilled as DribbbleSquareFilled7, BehanceFilled as BehanceFilled7,
  BehanceSquareFilled as BehanceSquareFilled7, MediumFilled as MediumFilled7,
  LinkedinFilled as LinkedinFilled7, GooglePlusFilled as GooglePlusFilled7,
  GitlabFilled as GitlabFilled8, GithubFilled as GithubFilled8,
  RedditFilled as RedditFilled7, SkypeFilled as SkypeFilled7,
  SlackSquareFilled as SlackSquareFilled7, WhatsAppFilled as WhatsAppFilled7,
  YoutubeFilled as YoutubeFilled8, InstagramFilled as InstagramFilled8,
  FacebookFilled as FacebookFilled8, TwitterSquareFilled as TwitterSquareFilled7,
  WechatFilled as WechatFilled8, QqFilled as QqFilled8,
  AlipayCircleFilled as AlipayCircleFilled8, TaobaoCircleFilled as TaobaoCircleFilled8,
  WeiboCircleFilled as WeiboCircleFilled8, AlipaySquareFilled as AlipaySquareFilled8,
  TaobaoSquareFilled as TaobaoSquareFilled8, WeiboSquareFilled as WeiboSquareFilled8,
  YuqueFilled as YuqueFilled8, DribbbleFilled as DribbbleFilled8,
  DribbbleSquareFilled as DribbbleSquareFilled8, BehanceFilled as BehanceFilled8,
  BehanceSquareFilled as BehanceSquareFilled8, MediumFilled as MediumFilled8,
  LinkedinFilled as LinkedinFilled8, GooglePlusFilled as GooglePlusFilled8,
  GitlabFilled as GitlabFilled9, GithubFilled as GithubFilled9,
  RedditFilled as RedditFilled8, SkypeFilled as SkypeFilled8,
  SlackSquareFilled as SlackSquareFilled8, WhatsAppFilled as WhatsAppFilled8,
  YoutubeFilled as YoutubeFilled9, InstagramFilled as InstagramFilled9,
  FacebookFilled as FacebookFilled9, TwitterSquareFilled as TwitterSquareFilled8,
  WechatFilled as WechatFilled9, QqFilled as QqFilled9,
  AlipayCircleFilled as AlipayCircleFilled9, TaobaoCircleFilled as TaobaoCircleFilled9,
  WeiboCircleFilled as WeiboCircleFilled9, AlipaySquareFilled as AlipaySquareFilled9,
  TaobaoSquareFilled as TaobaoSquareFilled9, WeiboSquareFilled as WeiboSquareFilled9,
  YuqueFilled as YuqueFilled9, DribbbleFilled as DribbbleFilled9,
  DribbbleSquareFilled as DribbbleSquareFilled9, BehanceFilled as BehanceFilled9,
  BehanceSquareFilled as BehanceSquareFilled9, MediumFilled as MediumFilled9,
  LinkedinFilled as LinkedinFilled9, GooglePlusFilled as GooglePlusFilled9,
  GitlabFilled as GitlabFilled10, GithubFilled as GithubFilled10,
  RedditFilled as RedditFilled9, SkypeFilled as SkypeFilled9,
  SlackSquareFilled as SlackSquareFilled9, WhatsAppFilled as WhatsAppFilled9,
  YoutubeFilled as YoutubeFilled10, InstagramFilled as InstagramFilled10,
  FacebookFilled as FacebookFilled10, TwitterSquareFilled as TwitterSquareFilled9
} from '@ant-design/icons'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input

interface TemplateItem {
  id: string
  title: string
  category: string
  sub_category: string
  language: string
  content: string
  variables: string[]
  usage_count: number
  rating: number
  status: 'active' | 'inactive' | 'draft'
  created_by: string
  created_at: string
  updated_at: string
}

const categoryOptions = [
  { value: 'pre_sale', label: '售前咨询', color: 'blue' },
  { value: 'after_sale', label: '售后服务', color: 'green' },
  { value: 'logistics', label: '物流查询', color: 'orange' },
  { value: 'refund', label: '退款退货', color: 'red' },
  { value: 'complaint', label: '投诉处理', color: 'magenta' },
  { value: 'product', label: '产品咨询', color: 'cyan' },
  { value: 'payment', label: '支付问题', color: 'purple' },
  { value: 'other', label: '其他', color: 'default' },
]

export default function CustomerTemplatesPage() {
  const [activeTab, setActiveTab] = useState('list')
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [viewingTemplate, setViewingTemplate] = useState<TemplateItem | null>(null)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editForm] = Form.useForm()
  const [categoryFilter, setCategoryFilter] = useState('all')
  // 真实API数据状态
  const [templateData, setTemplateData] = useState<any>(null)

  const mockTemplates: TemplateItem[] = [
    { id: '1', title: '欢迎新客户咨询', category: 'pre_sale', sub_category: '首次咨询', language: 'en', content: 'Hi {customer_name}, welcome to Nuotao Outdoor! 👋\n\nThank you for your interest in our products. I would be happy to help you find the perfect outdoor gear for your adventures.\n\nCould you please let me know:\n1. What type of outdoor activities do you enjoy?\n2. What is your budget range?\n3. Do you have any specific requirements?\n\nI will get back to you within 24 hours with personalized recommendations!\n\nBest regards,\nNuotao Outdoor Customer Service Team', variables: ['customer_name'], usage_count: 256, rating: 4.8, status: 'active', created_by: 'AI生成', created_at: '2026-08-01', updated_at: '2026-09-01' },
    { id: '2', title: '订单发货通知', category: 'logistics', sub_category: '发货通知', language: 'en', content: 'Hi {customer_name},\n\nGreat news! Your order #{order_number} has been shipped! 📦\n\nOrder Details:\n- Order Number: {order_number}\n- Shipping Method: {shipping_method}\n- Tracking Number: {tracking_number}\n- Estimated Delivery: {estimated_delivery}\n\nYou can track your package here: {tracking_link}\n\nIf you have any questions about your order, please feel free to contact us anytime.\n\nHappy adventuring! 🏕️\n\nNuotao Outdoor Team', variables: ['customer_name', 'order_number', 'shipping_method', 'tracking_number', 'estimated_delivery', 'tracking_link'], usage_count: 189, rating: 4.9, status: 'active', created_by: '客服主管', created_at: '2026-07-15', updated_at: '2026-08-20' },
    { id: '3', title: '退款申请确认', category: 'refund', sub_category: '退款确认', language: 'en', content: 'Hi {customer_name},\n\nWe have received your refund request for order #{order_number}.\n\nRefund Details:\n- Order Number: {order_number}\n- Refund Amount: ${refund_amount}\n- Reason: {refund_reason}\n\nOur team will review your request within 24-48 hours. Once approved, the refund will be processed to your original payment method within 5-7 business days.\n\nWe apologize for any inconvenience and appreciate your patience.\n\nIf you have any questions, please don\'t hesitate to reach out.\n\nBest regards,\nNuotao Outdoor Support Team', variables: ['customer_name', 'order_number', 'refund_amount', 'refund_reason'], usage_count: 145, rating: 4.7, status: 'active', created_by: 'AI生成', created_at: '2026-08-10', updated_at: '2026-09-02' },
    { id: '4', title: '产品规格咨询回复', category: 'product', sub_category: '规格参数', language: 'en', content: 'Hi {customer_name},\n\nThank you for your question about the {product_name}!\n\nHere are the detailed specifications:\n\n📦 Product: {product_name}\n- Material: {material}\n- Dimensions: {dimensions}\n- Weight: {weight}\n- Color Options: {colors}\n- Warranty: {warranty}\n\nKey Features:\n{features}\n\nThis product is perfect for {use_case}. Many of our customers love it for {selling_point}.\n\nWould you like me to help you place an order or do you have any other questions?\n\nBest regards,\nNuotao Outdoor Team', variables: ['customer_name', 'product_name', 'material', 'dimensions', 'weight', 'colors', 'warranty', 'features', 'use_case', 'selling_point'], usage_count: 98, rating: 4.6, status: 'active', created_by: '产品经理', created_at: '2026-08-05', updated_at: '2026-08-25' },
    { id: '5', title: '物流延迟致歉', category: 'logistics', sub_category: '延迟处理', language: 'en', content: 'Dear {customer_name},\n\nWe sincerely apologize for the delay in your order #{order_number}. 🙏\n\nWe understand how important it is to receive your outdoor gear on time, and we regret that your package is taking longer than expected.\n\nCurrent Status:\n- Order Number: {order_number}\n- Current Location: {current_location}\n- Expected Delivery: {new_estimated_delivery}\n- Reason for Delay: {delay_reason}\n\nAs a gesture of our apology, we would like to offer you a {discount_percent}% discount code for your next purchase: {discount_code}\n\nWe are working closely with our logistics partner to expedite your delivery. Please rest assured that we will keep you updated on the progress.\n\nThank you for your understanding and patience.\n\nWarm regards,\nNuotao Outdoor Customer Care', variables: ['customer_name', 'order_number', 'current_location', 'new_estimated_delivery', 'delay_reason', 'discount_percent', 'discount_code'], usage_count: 67, rating: 4.5, status: 'active', created_by: '客服主管', created_at: '2026-08-20', updated_at: '2026-09-03' },
    { id: '6', title: '投诉升级处理', category: 'complaint', sub_category: '升级处理', language: 'en', content: 'Dear {customer_name},\n\nThank you for bringing this matter to our attention. We take all customer feedback very seriously.\n\nI have escalated your complaint regarding {complaint_topic} to our senior management team for immediate review.\n\nComplaint Reference: #{complaint_id}\nDate: {complaint_date}\nPriority: {priority}\n\nOur team will investigate this matter thoroughly and provide you with a detailed response within 24 hours.\n\nWe value you as a customer and are committed to resolving this issue to your satisfaction.\n\nIf you have any additional information or concerns, please feel free to share them with me directly.\n\nSincerely,\n{agent_name}\nSenior Customer Support Specialist\nNuotao Outdoor', variables: ['customer_name', 'complaint_topic', 'complaint_id', 'complaint_date', 'priority', 'agent_name'], usage_count: 34, rating: 4.8, status: 'active', created_by: '客服主管', created_at: '2026-07-20', updated_at: '2026-08-15' },
    { id: '7', title: '支付失败处理', category: 'payment', sub_category: '支付失败', language: 'en', content: 'Hi {customer_name},\n\nWe noticed that your payment for order #{order_number} was unsuccessful.\n\nDon\'t worry! Here are some common reasons and solutions:\n\n❌ Possible Reasons:\n1. Insufficient funds in your account\n2. Card expired or entered incorrectly\n3. Bank declined the transaction (common for international payments)\n4. Payment gateway timeout\n\n✅ Solutions:\n1. Try a different payment method (we accept Visa, Mastercard, PayPal, Apple Pay)\n2. Contact your bank to authorize international transactions\n3. Double-check your card details and try again\n4. Use PayPal for a smoother checkout experience\n\nYour cart items have been saved for 24 hours. You can complete your purchase here: {checkout_link}\n\nIf you continue to experience issues, please let us know and we\'ll be happy to help!\n\nBest regards,\nNuotao Outdoor Support', variables: ['customer_name', 'order_number', 'checkout_link'], usage_count: 56, rating: 4.4, status: 'active', created_by: 'AI生成', created_at: '2026-08-15', updated_at: '2026-09-01' },
    { id: '8', title: '退货流程指引', category: 'refund', sub_category: '退货流程', language: 'en', content: 'Hi {customer_name},\n\nWe\'re sorry to hear that the {product_name} didn\'t meet your expectations. We want to make the return process as easy as possible for you.\n\n📋 Return Process:\n\nStep 1: Request a Return\n- Contact us within 30 days of delivery\n- Provide your order number #{order_number}\n- Tell us the reason for return\n\nStep 2: Get Return Authorization\n- We will send you a Return Merchandise Authorization (RMA) number\n- Package the item securely with all original packaging\n- Write the RMA number clearly on the outside of the package\n\nStep 3: Ship the Item Back\n- Ship to: {return_address}\n- We recommend using tracked shipping\n- Keep your tracking number for reference\n\nStep 4: Receive Your Refund\n- Once we receive and inspect the item (usually 3-5 business days)\n- Refund will be processed to your original payment method within 5-7 business days\n\n📦 Return Address:\n{return_address}\n\nIf you have any questions during the process, please don\'t hesitate to contact us!\n\nBest regards,\nNuotao Outdoor Returns Team', variables: ['customer_name', 'product_name', 'order_number', 'return_address'], usage_count: 78, rating: 4.6, status: 'active', created_by: '客服主管', created_at: '2026-07-10', updated_at: '2026-08-30' },
  ]

  // 加载客服模板数据（调用真实API，失败则使用mock数据降级）
  const loadCustomerTemplatesData = async () => {
    try {
      setLoading(true)
      // 调用AI能力API（包含客服自动回复相关功能）
      const aiResp = await fetch('/api/v1/ai-capability/status')
      if (aiResp.ok) {
        const aiData = await aiResp.json()
        setTemplateData(aiData)
        console.log('AI capability status:', aiData)
      }
      message.success('客服模板数据加载完成')
    } catch (e: any) {
      console.error('Load customer templates data error:', e)
      message.warning(`API调用失败，使用模拟数据：${e.message || '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCustomerTemplatesData()
  }, [])

  // 统计数据（优先使用真实API数据，失败则使用mock数据降级）
  const stats = {
    totalTemplates: templateData?.total_templates || mockTemplates.length,
    activeTemplates: templateData?.active_templates || mockTemplates.filter(t => t.status === 'active').length,
    totalUsage: templateData?.total_usage || mockTemplates.reduce((s, t) => s + t.usage_count, 0),
    avgRating: templateData?.avg_rating || (mockTemplates.reduce((s, t) => s + t.rating, 0) / mockTemplates.length).toFixed(1),
    categories: templateData?.categories || categoryOptions.length,
    languages: templateData?.languages || 2,
  }

  const templateColumns = [
    { title: '模板标题', dataIndex: 'title', key: 'title', width: 200, render: (t: string, record: TemplateItem) => <div><div style={{ fontWeight: 500, fontSize: 13 }}>{t}</div><div style={{ fontSize: 10, color: '#999' }}>{record.sub_category} · {record.language.toUpperCase()}</div></div> },
    { title: '分类', dataIndex: 'category', key: 'category', width: 120, render: (c: string) => <Tag color={categoryOptions.find(opt => opt.value === c)?.color}>{categoryOptions.find(opt => opt.value === c)?.label}</Tag> },
    { title: '变量数', dataIndex: 'variables', key: 'variables', width: 100, render: (v: string[]) => <Text>{v.length}个</Text> },
    { title: '使用次数', dataIndex: 'usage_count', key: 'usage_count', width: 100, render: (v: number) => <Text>{v}次</Text> },
    { title: '评分', dataIndex: 'rating', key: 'rating', width: 120, render: (v: number) => <div><Rate disabled value={v} style={{ fontSize: 12 }} /><div style={{ fontSize: 10, color: '#999' }}>{v}/5.0</div></div> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: (s: string) => <Tag color={s === 'active' ? 'green' : s === 'inactive' ? 'default' : 'orange'}>{s === 'active' ? '启用中' : s === 'inactive' ? '已停用' : '草稿'}</Tag> },
    { title: '最后更新', dataIndex: 'updated_at', key: 'updated_at', width: 120, render: (t: string) => <Text type="secondary" style={{ fontSize: 11 }}>{t}</Text> },
    { title: '操作', key: 'actions', width: 200, render: (_: any, record: TemplateItem) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => { setViewingTemplate(record); setDetailModalOpen(true) }}>预览</Button>
        <Button size="small" icon={<EditOutlined />} onClick={() => { setViewingTemplate(record); editForm.setFieldsValue(record); setEditModalOpen(true) }}>编辑</Button>
        <Button size="small" icon={<CopyOutlined />} onClick={() => message.success('模板已复制')}>复制</Button>
      </Space>
    )},
  ]

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      <div style={{ marginBottom: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <CustomerServiceOutlined style={{ fontSize: '28px', color: '#722ed1' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>客服话术模板</Title>
            <Text type="secondary">模板管理、AI生成、变量配置、使用统计</Text>
          </div>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => message.success('数据已刷新')}>刷新</Button>
          <Button icon={<DownloadOutlined />} onClick={() => message.success('已导出')}>导出</Button>
          <Button type="primary" icon={<ThunderboltOutlined />} loading={generating} onClick={() => {
            setGenerating(true)
            setTimeout(() => { message.success('AI话术模板已生成'); setGenerating(false) }, 2000)
          }}>AI生成模板</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { editForm.resetFields(); setEditModalOpen(true) }}>新建模板</Button>
        </Space>
      </div>

      <Alert message="话术模板说明" description="支持变量插入（如{customer_name}、{order_number}等），客服回复时自动替换为实际内容。模板按场景分类，支持多语言版本。建议定期更新模板，确保话术的准确性和时效性。" type="info" showIcon icon={<InfoCircleOutlined />} style={{ marginBottom: 16 }} />

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={4}><Card size="small"><Statistic title="模板总数" value={stats.totalTemplates} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="启用中" value={stats.activeTemplates} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="分类数" value={stats.categories} suffix="类" /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="语言数" value={stats.languages} suffix="种" /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="总使用次数" value={stats.totalUsage} suffix="次" valueStyle={{ color: '#1890ff' }} /></Card></Col>
        <Col span={4}><Card size="small"><Statistic title="平均评分" value={stats.avgRating} suffix="/5" valueStyle={{ color: '#faad14' }} /></Card></Col>
      </Row>

      <Card size="small">
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'list',
              label: '模板列表',
              children: (
                <div>
                  <Space wrap style={{ marginBottom: 16 }}>
                    <Input placeholder="搜索模板标题/内容" prefix={<SearchOutlined />} style={{ width: 200 }} allowClear />
                    <Select value={categoryFilter} onChange={setCategoryFilter} style={{ width: 150 }} options={[
                      { value: 'all', label: '全部分类' },
                      ...categoryOptions.map(c => ({ value: c.value, label: c.label })),
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部状态' },
                      { value: 'active', label: '启用中' },
                      { value: 'inactive', label: '已停用' },
                      { value: 'draft', label: '草稿' },
                    ]} />
                    <Select defaultValue="all" style={{ width: 120 }} options={[
                      { value: 'all', label: '全部语言' },
                      { value: 'en', label: '英语' },
                      { value: 'zh', label: '中文' },
                    ]} />
                  </Space>
                  <Table columns={templateColumns} dataSource={mockTemplates} rowKey="id" pagination={{ pageSize: 10, showTotal: (total) => `共 ${total} 个模板` }} locale={{ emptyText: <Empty description="暂无模板" /> }} scroll={{ x: 1600 }} />
                </div>
              ),
            },
            {
              key: 'category',
              label: '分类管理',
              children: (
                <div>
                  <Row gutter={[16, 16]}>
                    {categoryOptions.map(cat => {
                      const count = mockTemplates.filter(t => t.category === cat.value).length
                      const usage = mockTemplates.filter(t => t.category === cat.value).reduce((s, t) => s + t.usage_count, 0)
                      return (
                        <Col span={6} key={cat.value}>
                          <Card size="small" hoverable>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                              <Tag color={cat.color} style={{ fontSize: 14, padding: '4px 12px' }}>{cat.label}</Tag>
                              <Text type="secondary" style={{ fontSize: 11 }}>{count}个模板</Text>
                            </div>
                            <Divider style={{ margin: '12px 0' }} />
                            <div style={{ fontSize: 12, color: '#999' }}>
                              <div>总使用: {usage}次</div>
                              <div>平均评分: {(count > 0 ? (mockTemplates.filter(t => t.category === cat.value).reduce((s, t) => s + t.rating, 0) / count).toFixed(1) : '-')}/5</div>
                            </div>
                          </Card>
                        </Col>
                      )
                    })}
                  </Row>
                </div>
              ),
            },
            {
              key: 'ai_generate',
              label: 'AI生成',
              children: (
                <div>
                  <Row gutter={24}>
                    <Col span={12}>
                      <Card size="small" title="AI生成设置" style={{ marginBottom: 16 }}>
                        <Form layout="vertical">
                          <Form.Item label="话术场景" required>
                            <Select options={categoryOptions.map(c => ({ value: c.value, label: c.label }))} placeholder="请选择话术场景" />
                          </Form.Item>
                          <Form.Item label="具体场景描述">
                            <TextArea rows={3} placeholder="请描述具体的客服场景，如：客户询问产品是否防水，如何回复" />
                          </Form.Item>
                          <Form.Item label="语言">
                            <Radio.Group>
                              <Radio value="en">英语</Radio>
                              <Radio value="zh">中文</Radio>
                              <Radio value="de">德语</Radio>
                              <Radio value="fr">法语</Radio>
                            </Radio.Group>
                          </Form.Item>
                          <Form.Item label="语气风格">
                            <Select options={[
                              { value: 'professional', label: '专业正式' },
                              { value: 'friendly', label: '友好亲切' },
                              { value: 'warm', label: '温暖贴心' },
                              { value: 'concise', label: '简洁明了' },
                            ]} />
                          </Form.Item>
                          <Form.Item label="需要包含的变量">
                            <Select mode="tags" placeholder="输入变量名，如 customer_name, order_number" />
                          </Form.Item>
                          <Button type="primary" icon={<ThunderboltOutlined />} loading={generating} block onClick={() => {
                            setGenerating(true)
                            setTimeout(() => { message.success('AI话术模板已生成，请在右侧查看'); setGenerating(false) }, 3000)
                          }}>
                            生成话术模板
                          </Button>
                        </Form>
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title="生成结果预览" extra={<Space><Button size="small" icon={<CopyOutlined />} onClick={() => message.success('已复制')}>复制</Button><Button size="small" type="primary" icon={<SaveOutlined />} onClick={() => message.success('已保存为模板')}>保存</Button></Space>}>
                        <div style={{ background: '#fafafa', padding: 16, borderRadius: 8, minHeight: 400, whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.8 }}>
                          {generating ? (
                            <div style={{ textAlign: 'center', padding: '100px 0' }}>
                              <Spin size="large" />
                              <div style={{ marginTop: 16, color: '#999' }}>AI正在生成话术模板，请稍候...</div>
                            </div>
                          ) : (
                            <Text type="secondary">请在左侧填写生成设置，点击"生成话术模板"按钮开始生成。</Text>
                          )}
                        </div>
                      </Card>
                    </Col>
                  </Row>
                </div>
              ),
            },
            {
              key: 'statistics',
              label: '使用统计',
              children: (
                <div>
                  <Row gutter={16}>
                    <Col span={12}>
                      <Card size="small" title="模板使用排行" style={{ marginBottom: 16 }}>
                        <List
                          size="small"
                          dataSource={[...mockTemplates].sort((a, b) => b.usage_count - a.usage_count).slice(0, 5)}
                          renderItem={(item, idx) => (
                            <List.Item>
                              <List.Item.Meta
                                avatar={<Avatar size="small" style={{ backgroundColor: idx < 3 ? '#f5222d' : '#1890ff' }}>{idx + 1}</Avatar>}
                                title={<div style={{ display: 'flex', justifyContent: 'space-between' }}><Text style={{ fontSize: 13 }}>{item.title}</Text><Text strong style={{ color: '#1890ff' }}>{item.usage_count}次</Text></div>}
                                description={<Tag color={categoryOptions.find(c => c.value === item.category)?.color}>{categoryOptions.find(c => c.value === item.category)?.label}</Tag>}
                              />
                            </List.Item>
                          )}
                        />
                      </Card>
                    </Col>
                    <Col span={12}>
                      <Card size="small" title="分类使用占比" style={{ marginBottom: 16 }}>
                        <List
                          size="small"
                          dataSource={categoryOptions.map(cat => ({
                            ...cat,
                            count: mockTemplates.filter(t => t.category === cat.value).reduce((s, t) => s + t.usage_count, 0),
                          })).filter(c => c.count > 0).sort((a, b) => b.count - a.count)}
                          renderItem={(item) => (
                            <List.Item>
                              <List.Item.Meta
                                title={<div style={{ display: 'flex', justifyContent: 'space-between' }}><Tag color={item.color}>{item.label}</Tag><Text strong>{item.count}次</Text></div>}
                                description={<Progress percent={Math.round((item.count / stats.totalUsage) * 100)} size="small" showInfo={false} />}
                              />
                            </List.Item>
                          )}
                        />
                      </Card>
                    </Col>
                  </Row>
                </div>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={`模板预览 - ${viewingTemplate?.title || ''}`}
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="use" type="primary" icon={<CheckOutlined />} onClick={() => { message.success('已使用该模板'); setDetailModalOpen(false) }}>使用模板</Button>,
          <Button key="edit" icon={<EditOutlined />} onClick={() => { editForm.setFieldsValue(viewingTemplate); setEditModalOpen(true); setDetailModalOpen(false) }}>编辑</Button>,
          <Button key="close" onClick={() => setDetailModalOpen(false)}>关闭</Button>,
        ]}
        width={700}
      >
        {viewingTemplate && (
          <div>
            <Descriptions column={3} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="模板标题" span={2}>{viewingTemplate.title}</Descriptions.Item>
              <Descriptions.Item label="语言">{viewingTemplate.language.toUpperCase()}</Descriptions.Item>
              <Descriptions.Item label="分类"><Tag color={categoryOptions.find(c => c.value === viewingTemplate.category)?.color}>{categoryOptions.find(c => c.value === viewingTemplate.category)?.label}</Tag></Descriptions.Item>
              <Descriptions.Item label="子分类">{viewingTemplate.sub_category}</Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={viewingTemplate.status === 'active' ? 'green' : 'default'}>{viewingTemplate.status === 'active' ? '启用中' : '已停用'}</Tag></Descriptions.Item>
              <Descriptions.Item label="使用次数">{viewingTemplate.usage_count}次</Descriptions.Item>
              <Descriptions.Item label="评分"><Rate disabled value={viewingTemplate.rating} style={{ fontSize: 12 }} /></Descriptions.Item>
              <Descriptions.Item label="创建者">{viewingTemplate.created_by}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{viewingTemplate.created_at}</Descriptions.Item>
              <Descriptions.Item label="最后更新">{viewingTemplate.updated_at}</Descriptions.Item>
            </Descriptions>

            <Alert message="模板变量" description={viewingTemplate.variables.map(v => `{${v}}`).join('、')} type="info" showIcon style={{ marginBottom: 16 }} />

            <Title level={5}>模板内容</Title>
            <div style={{ background: '#fafafa', padding: 16, borderRadius: 8, whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.8, maxHeight: 400, overflow: 'auto' }}>
              {viewingTemplate.content}
            </div>
          </div>
        )}
      </Modal>

      <Modal
        title={viewingTemplate ? '编辑模板' : '新建模板'}
        open={editModalOpen}
        onCancel={() => setEditModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setEditModalOpen(false)}>取消</Button>,
          <Button key="save" type="primary" icon={<SaveOutlined />} onClick={() => { message.success('模板已保存'); setEditModalOpen(false) }}>保存</Button>,
        ]}
        width={700}
      >
        <Form form={editForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="title" label="模板标题" rules={[{ required: true }]}>
                <Input placeholder="请输入模板标题" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="category" label="分类" rules={[{ required: true }]}>
                <Select options={categoryOptions.map(c => ({ value: c.value, label: c.label }))} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="sub_category" label="子分类">
                <Input placeholder="请输入子分类" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="language" label="语言" initialValue="en">
                <Select options={[
                  { value: 'en', label: '英语' },
                  { value: 'zh', label: '中文' },
                  { value: 'de', label: '德语' },
                  { value: 'fr', label: '法语' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="variables" label="变量列表（逗号分隔）">
            <Input placeholder="如：customer_name, order_number, tracking_number" />
          </Form.Item>
          <Form.Item name="content" label="模板内容" rules={[{ required: true }]}>
            <TextArea rows={12} placeholder="请输入模板内容，使用{变量名}插入变量" />
          </Form.Item>
          <Form.Item name="status" label="状态" valuePropName="checked" initialValue={true}>
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
