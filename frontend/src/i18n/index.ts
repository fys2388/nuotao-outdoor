/**
 * 多语言配置框架
 * 支持中文、英文、日文等多语言切换
 */

// 语言类型
export type Language = 'zh-CN' | 'en-US' | 'ja-JP';

// 语言配置
export const LANGUAGES: { code: Language; name: string; flag: string }[] = [
  { code: 'zh-CN', name: '简体中文', flag: '🇨🇳' },
  { code: 'en-US', name: 'English', flag: '🇺🇸' },
  { code: 'ja-JP', name: '日本語', flag: '🇯🇵' },
];

// 默认语言
export const DEFAULT_LANGUAGE: Language = 'zh-CN';

// 本地存储键
const LANGUAGE_STORAGE_KEY = 'nuotao-language';

// 获取当前语言
export function getCurrentLanguage(): Language {
  const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY);
  if (saved && LANGUAGES.some(l => l.code === saved)) {
    return saved as Language;
  }
  // 检测浏览器语言
  const browserLang = navigator.language;
  if (browserLang.startsWith('zh')) return 'zh-CN';
  if (browserLang.startsWith('ja')) return 'ja-JP';
  return 'en-US';
}

// 设置语言
export function setLanguage(lang: Language): void {
  localStorage.setItem(LANGUAGE_STORAGE_KEY, lang);
  document.documentElement.lang = lang;
  // 触发语言变更事件
  window.dispatchEvent(new CustomEvent('language-change', { detail: { language: lang } }));
}

// 翻译函数类型
export type TranslateFunction = (key: string, params?: Record<string, string | number>) => string;

// 翻译字典类型
export type TranslationDict = Record<string, string>;

// 中文翻译
export const zhCN: TranslationDict = {
  // 通用
  'common.confirm': '确认',
  'common.cancel': '取消',
  'common.save': '保存',
  'common.delete': '删除',
  'common.edit': '编辑',
  'common.search': '搜索',
  'common.loading': '加载中...',
  'common.success': '操作成功',
  'common.error': '操作失败',
  'common.noData': '暂无数据',

  // 导航
  'nav.dashboard': '经营看板',
  'nav.orders': '订单管理',
  'nav.products': '产品管理',
  'nav.customers': '客户管理',
  'nav.procurement': '采购管理',
  'nav.inventory': '库存管理',
  'nav.logistics': '物流管理',
  'nav.finance': '财务管理',
  'nav.marketing': '营销管理',
  'nav.ai': 'AI能力',
  'nav.settings': '系统设置',

  // 仪表盘
  'dashboard.title': '经营看板',
  'dashboard.todayRevenue': '今日营收',
  'dashboard.todayOrders': '今日订单',
  'dashboard.todayCustomers': '今日新增客户',
  'dashboard.conversionRate': '转化率',

  // 订单
  'orders.title': '订单管理',
  'orders.orderId': '订单号',
  'orders.customer': '客户',
  'orders.amount': '金额',
  'orders.status': '状态',
  'orders.date': '日期',

  // 产品
  'products.title': '产品管理',
  'products.name': '产品名称',
  'products.sku': 'SKU',
  'products.price': '价格',
  'products.stock': '库存',
  'products.category': '分类',

  // 客户
  'customers.title': '客户管理',
  'customers.name': '客户姓名',
  'customers.email': '邮箱',
  'customers.phone': '电话',
  'customers.orders': '订单数',
  'customers.totalSpent': '消费总额',

  // 采购
  'procurement.title': '采购管理',
  'procurement.supplier': '供应商',
  'procurement.quantity': '数量',
  'procurement.cost': '成本',
  'procurement.status': '状态',

  // 库存
  'inventory.title': '库存管理',
  'inventory.warehouse': '仓库',
  'inventory.product': '产品',
  'inventory.quantity': '数量',
  'inventory.lowStock': '低库存预警',

  // 物流
  'logistics.title': '物流管理',
  'logistics.trackingNumber': '追踪号',
  'logistics.carrier': '物流公司',
  'logistics.status': '状态',
  'logistics.estimatedDelivery': '预计送达',

  // 财务
  'finance.title': '财务管理',
  'finance.revenue': '收入',
  'finance.expense': '支出',
  'finance.profit': '利润',
  'finance.cost': '成本',

  // 营销
  'marketing.title': '营销管理',
  'marketing.campaign': '活动',
  'marketing.channel': '渠道',
  'marketing.budget': '预算',
  'marketing.roi': 'ROI',

  // AI
  'ai.title': 'AI能力中心',
  'ai.sourcing': 'AI选品',
  'ai.customerService': 'AI客服',
  'ai.pricing': '动态定价',
  'ai.content': '内容生成',

  // 设置
  'settings.title': '系统设置',
  'settings.general': '通用设置',
  'settings.notifications': '通知设置',
  'settings.security': '安全设置',
  'settings.integrations': '集成设置',
};

// 英文翻译
export const enUS: TranslationDict = {
  // Common
  'common.confirm': 'Confirm',
  'common.cancel': 'Cancel',
  'common.save': 'Save',
  'common.delete': 'Delete',
  'common.edit': 'Edit',
  'common.search': 'Search',
  'common.loading': 'Loading...',
  'common.success': 'Success',
  'common.error': 'Error',
  'common.noData': 'No data',

  // Navigation
  'nav.dashboard': 'Dashboard',
  'nav.orders': 'Orders',
  'nav.products': 'Products',
  'nav.customers': 'Customers',
  'nav.procurement': 'Procurement',
  'nav.inventory': 'Inventory',
  'nav.logistics': 'Logistics',
  'nav.finance': 'Finance',
  'nav.marketing': 'Marketing',
  'nav.ai': 'AI Center',
  'nav.settings': 'Settings',

  // Dashboard
  'dashboard.title': 'Dashboard',
  'dashboard.todayRevenue': "Today's Revenue",
  'dashboard.todayOrders': "Today's Orders",
  'dashboard.todayCustomers': "Today's New Customers",
  'dashboard.conversionRate': 'Conversion Rate',

  // Orders
  'orders.title': 'Order Management',
  'orders.orderId': 'Order ID',
  'orders.customer': 'Customer',
  'orders.amount': 'Amount',
  'orders.status': 'Status',
  'orders.date': 'Date',

  // Products
  'products.title': 'Product Management',
  'products.name': 'Product Name',
  'products.sku': 'SKU',
  'products.price': 'Price',
  'products.stock': 'Stock',
  'products.category': 'Category',

  // Customers
  'customers.title': 'Customer Management',
  'customers.name': 'Name',
  'customers.email': 'Email',
  'customers.phone': 'Phone',
  'customers.orders': 'Orders',
  'customers.totalSpent': 'Total Spent',

  // Procurement
  'procurement.title': 'Procurement',
  'procurement.supplier': 'Supplier',
  'procurement.quantity': 'Quantity',
  'procurement.cost': 'Cost',
  'procurement.status': 'Status',

  // Inventory
  'inventory.title': 'Inventory',
  'inventory.warehouse': 'Warehouse',
  'inventory.product': 'Product',
  'inventory.quantity': 'Quantity',
  'inventory.lowStock': 'Low Stock Alert',

  // Logistics
  'logistics.title': 'Logistics',
  'logistics.trackingNumber': 'Tracking #',
  'logistics.carrier': 'Carrier',
  'logistics.status': 'Status',
  'logistics.estimatedDelivery': 'Est. Delivery',

  // Finance
  'finance.title': 'Finance',
  'finance.revenue': 'Revenue',
  'finance.expense': 'Expense',
  'finance.profit': 'Profit',
  'finance.cost': 'Cost',

  // Marketing
  'marketing.title': 'Marketing',
  'marketing.campaign': 'Campaign',
  'marketing.channel': 'Channel',
  'marketing.budget': 'Budget',
  'marketing.roi': 'ROI',

  // AI
  'ai.title': 'AI Center',
  'ai.sourcing': 'AI Sourcing',
  'ai.customerService': 'AI Customer Service',
  'ai.pricing': 'Dynamic Pricing',
  'ai.content': 'Content Generation',

  // Settings
  'settings.title': 'Settings',
  'settings.general': 'General',
  'settings.notifications': 'Notifications',
  'settings.security': 'Security',
  'settings.integrations': 'Integrations',
};

// 日文翻译（基础框架）
export const jaJP: TranslationDict = {
  // Common
  'common.confirm': '確認',
  'common.cancel': 'キャンセル',
  'common.save': '保存',
  'common.delete': '削除',
  'common.edit': '編集',
  'common.search': '検索',
  'common.loading': '読み込み中...',
  'common.success': '成功',
  'common.error': 'エラー',
  'common.noData': 'データなし',

  // Navigation
  'nav.dashboard': 'ダッシュボード',
  'nav.orders': '注文管理',
  'nav.products': '商品管理',
  'nav.customers': '顧客管理',
  'nav.procurement': '調達管理',
  'nav.inventory': '在庫管理',
  'nav.logistics': '物流管理',
  'nav.finance': '財務管理',
  'nav.marketing': 'マーケティング',
  'nav.ai': 'AIセンター',
  'nav.settings': '設定',

  // Dashboard
  'dashboard.title': 'ダッシュボード',
  'dashboard.todayRevenue': '今日の収益',
  'dashboard.todayOrders': '今日の注文',
  'dashboard.todayCustomers': '今日の新規顧客',
  'dashboard.conversionRate': 'コンバージョン率',

  // Orders
  'orders.title': '注文管理',
  'orders.orderId': '注文ID',
  'orders.customer': '顧客',
  'orders.amount': '金額',
  'orders.status': 'ステータス',
  'orders.date': '日付',

  // Products
  'products.title': '商品管理',
  'products.name': '商品名',
  'products.sku': 'SKU',
  'products.price': '価格',
  'products.stock': '在庫',
  'products.category': 'カテゴリ',

  // Customers
  'customers.title': '顧客管理',
  'customers.name': '名前',
  'customers.email': 'メール',
  'customers.phone': '電話',
  'customers.orders': '注文数',
  'customers.totalSpent': '合計支出',

  // 其他字段使用英文作为fallback
};

// 所有翻译字典
export const translations: Record<Language, TranslationDict> = {
  'zh-CN': zhCN,
  'en-US': enUS,
  'ja-JP': jaJP,
};

// 创建翻译函数
export function createTranslator(lang: Language): TranslateFunction {
  const dict = translations[lang] || translations[DEFAULT_LANGUAGE];
  const fallbackDict = translations[DEFAULT_LANGUAGE];

  return (key: string, params?: Record<string, string | number>): string => {
    let text = dict[key] || fallbackDict[key] || key;

    // 替换参数
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        text = text.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v));
      });
    }

    return text;
  };
}
