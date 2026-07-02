import { getLocale, type Locale } from "$lib/paraglide/runtime";

/**
 * デモ（「お試しはこちら」）環境の固定コンテンツ（プロジェクト名・機能名）を、選択言語で表示するための対訳表。
 *
 * これらは seed_demo.py が日本語で投入する DB データ（＝UI メッセージではない）なので Paraglide の辞書には
 * 載らない。ここでは日本語原文をキーに各言語の訳を持ち、`localizeDemoContent()` が現在ロケールの訳を返す。
 * ja・未登録文字列・空はそのまま返すため、実ユーザーの（デモでない）プロジェクト/機能名には影響しない。
 */
type Translations = Partial<Record<Locale, string>>;

const DEMO_CONTENT: Record<string, Translations> = {
  // --- プロジェクト名 ---
  "EC ストア": {
    en: "E-commerce Store",
    zh: "电商商店",
    ko: "이커머스 스토어",
    es: "Tienda online",
    de: "Onlineshop",
  },
  請求サービス: {
    en: "Billing Service",
    zh: "计费服务",
    ko: "청구 서비스",
    es: "Servicio de facturación",
    de: "Abrechnungsdienst",
  },
  在庫API: { en: "Inventory API", zh: "库存 API", ko: "재고 API", es: "API de inventario", de: "Bestands-API" },
  マーケLP: {
    en: "Marketing LP",
    zh: "营销落地页",
    ko: "마케팅 LP",
    es: "Landing de marketing",
    de: "Marketing-Landingpage",
  },
  社内ツール: {
    en: "Internal Tools",
    zh: "内部工具",
    ko: "사내 도구",
    es: "Herramientas internas",
    de: "Interne Tools",
  },
  モバイルアプリ: { en: "Mobile App", zh: "移动应用", ko: "모바일 앱", es: "App móvil", de: "Mobile App" },

  // --- 機能名（コア） ---
  "決済・カート": {
    en: "Checkout & Cart",
    zh: "结算与购物车",
    ko: "결제·장바구니",
    es: "Pago y carrito",
    de: "Checkout & Warenkorb",
  },
  認証: { en: "Authentication", zh: "认证", ko: "인증", es: "Autenticación", de: "Authentifizierung" },
  商品カタログ: {
    en: "Product Catalog",
    zh: "商品目录",
    ko: "상품 카탈로그",
    es: "Catálogo de productos",
    de: "Produktkatalog",
  },
  在庫: { en: "Inventory", zh: "库存", ko: "재고", es: "Inventario", de: "Bestand" },
  ユーザー: { en: "Users", zh: "用户", ko: "사용자", es: "Usuarios", de: "Benutzer" },
  配送: { en: "Shipping", zh: "配送", ko: "배송", es: "Envío", de: "Versand" },
  通知: { en: "Notifications", zh: "通知", ko: "알림", es: "Notificaciones", de: "Benachrichtigungen" },

  // --- 機能名（拡張） ---
  決済ゲートウェイ: {
    en: "Payment Gateway",
    zh: "支付网关",
    ko: "결제 게이트웨이",
    es: "Pasarela de pago",
    de: "Zahlungs-Gateway",
  },
  注文管理: {
    en: "Order Management",
    zh: "订单管理",
    ko: "주문 관리",
    es: "Gestión de pedidos",
    de: "Bestellverwaltung",
  },
  "レビュー・評価": {
    en: "Reviews & Ratings",
    zh: "评论与评分",
    ko: "리뷰·평점",
    es: "Reseñas y valoraciones",
    de: "Bewertungen & Rezensionen",
  },
  レコメンド: { en: "Recommendations", zh: "推荐", ko: "추천", es: "Recomendaciones", de: "Empfehlungen" },
  プロモーション: { en: "Promotions", zh: "促销", ko: "프로모션", es: "Promociones", de: "Aktionen" },
  管理画面: {
    en: "Admin Panel",
    zh: "管理后台",
    ko: "관리자 화면",
    es: "Panel de administración",
    de: "Admin-Bereich",
  },
  "分析・計測": { en: "Analytics", zh: "分析与统计", ko: "분석·계측", es: "Analítica", de: "Analyse & Messung" },
  "検索・インデックス": {
    en: "Search & Index",
    zh: "搜索与索引",
    ko: "검색·인덱스",
    es: "Búsqueda e índice",
    de: "Suche & Index",
  },
  コンテンツ管理: {
    en: "Content Management",
    zh: "内容管理",
    ko: "콘텐츠 관리",
    es: "Gestión de contenidos",
    de: "Content-Management",
  },
  共通基盤: {
    en: "Shared Platform",
    zh: "公共基础",
    ko: "공통 기반",
    es: "Plataforma común",
    de: "Gemeinsame Basis",
  },
  データモデル: { en: "Data Models", zh: "数据模型", ko: "데이터 모델", es: "Modelos de datos", de: "Datenmodelle" },
  "UI 部品": { en: "UI Components", zh: "UI 组件", ko: "UI 부품", es: "Componentes de UI", de: "UI-Komponenten" },
  "運用・外部連携・セキュリティ": {
    en: "Ops, Integrations & Security",
    zh: "运维·外部集成·安全",
    ko: "운영·외부 연동·보안",
    es: "Operaciones, integraciones y seguridad",
    de: "Betrieb, Integrationen & Sicherheit",
  },
  価格計算: {
    en: "Pricing",
    zh: "价格计算",
    ko: "가격 계산",
    es: "Cálculo de precios",
    de: "Preisberechnung",
  },
  お気に入り: { en: "Wishlist", zh: "收藏", ko: "위시리스트", es: "Favoritos", de: "Wunschliste" },
  サポート: { en: "Support", zh: "支持", ko: "지원", es: "Soporte", de: "Support" },
};

/**
 * デモ固定コンテンツ（プロジェクト名・機能名）を現在ロケールへ翻訳する。
 * ja・未登録・空文字はそのまま返すので、あらゆる name 描画箇所で無害に適用できる。
 */
export function localizeDemoContent(text: string | null | undefined): string {
  if (!text) return text ?? "";
  const locale = getLocale();
  if (locale === "ja") return text;
  return DEMO_CONTENT[text]?.[locale] ?? text;
}
