export type Role = "platform" | "leader" | "staff";
export type View = "dashboard" | "followups" | "orders" | "messages" | "customers" | "sales";
export type Lang = "fa" | "en";
export type SalesPeriod = "day" | "week" | "month" | "all";

export interface Session {
  role: Role;
  telegramId: number | null;
  csrf: string;
  staffId: number;
  displayName: string;
  username: string;
  permissions: string[];
}

export interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface DashboardData {
  role: Role;
  counts: Record<string, number>;
  sales: {
    period: SalesPeriod;
    orders: number;
    revenue: number | string;
    trend: Array<{ bucket: string; orders: number; revenue: number | string }>;
  };
  salesOpen: boolean;
  buyers: number;
  users: number;
  commission?: number;
  commissionPercent?: number;
}

export interface CustomerListItem {
  user_id: number;
  name?: string;
  first_name?: string;
  last_name?: string;
  username?: string;
  orders_count: number;
  total_spend: number | string;
  active_courses: number;
}

export interface ProductOption { id: number; title: string }
export interface CustomerPage extends PageResult<CustomerListItem> { products: ProductOption[] }

export interface OrderListItem {
  id: number;
  customer_id?: number;
  user_id?: number;
  telegram_id?: number;
  name?: string;
  first_name?: string;
  last_name?: string;
  username?: string;
  product_title: string;
  status: string;
  amount?: number | string;
  created_at?: string;
  updated_at?: string;
  payment_method?: string;
  payment_status?: string;
  paid_at?: string;
}

export interface OrderDetail extends OrderListItem {
  amount: number | string;
  phone?: string;
  paid_at?: string;
  delivered_at?: string;
  payment_method?: string;
  receipt_file_id?: boolean;
  receipt_type?: "photo" | "document";
  photo_count?: number;
  form_snapshot?: Record<string, unknown>;
  info_request?: string | null;
  gateway_ref?: string;
}

export interface OrderPage extends PageResult<OrderListItem> {
  counts: { actionable:number; receipts:number; new_orders:number; designing:number; needs_info:number };
}

export interface ThreadListItem {
  user_id: number;
  telegram_id?: number;
  name?: string;
  first_name?: string;
  last_name?: string;
  username?: string;
  last_message_at?: string;
  last_content_text?: string;
  last_content_type?: string;
  last_direction?: "customer" | "sensi";
  message_count: number;
  unread_count: number;
}

export interface ThreadPage extends PageResult<ThreadListItem> {
  counts: { all: number; unread_threads: number; unread_messages: number; assigned:number };
}

export interface FollowUpItem {
  target_type:"thread"|"customer"|"order";
  target_id:number;
  user_id:number;
  order_id?:number;
  telegram_id?:number;
  name?:string;
  first_name?:string;
  last_name?:string;
  username?:string;
  product_title?:string;
  note_body?:string;
  note_author?:string;
  note_created_at?:string;
  updated_at:string;
}

export interface FollowUpPage extends PageResult<FollowUpItem> { counts:ThreadPage["counts"] }

export interface MessageItem {
  id: number;
  direction: "customer" | "sensi";
  sender_name?: string;
  sender_staff_id?: number;
  content_text?: string;
  content_type?: string;
  has_attachment?: boolean;
  file_name?: string | null;
  mime_type?: string | null;
  file_size?: number | null;
  created_at?: string;
}

export interface UserDetail {
  id: number;
  telegram_id: number;
  name?: string;
  first_name?: string;
  last_name?: string;
  username?: string;
  phone?: string;
  age?: number;
  gender?: string;
  height_cm?: number;
  weight_kg?: number;
  goal?: string;
  training_history?: string;
  training_days?: number;
  nutrition_training_days?: number;
  workout_days?: number;
  food_allergy?: string;
  food_restriction?: string;
  supplements?: string;
  notes?: string;
  created_at?: string;
  updated_at?: string;
  photo_count?: number;
}

export interface CustomerDetailData {
  user: UserDetail;
  orders: OrderDetail[];
  history: Array<Record<string, unknown>>;
  messages: MessageItem[];
}

export interface ThreadDetailData { user: UserDetail; items: MessageItem[] }

export interface SalesData {
  period: SalesPeriod;
  revenue: number | string;
  orders: number;
  trend: Array<{ bucket: string; orders: number; revenue: number | string }>;
  items: Array<{
    order_id: number;
    user_id: number;
    name?: string;
    first_name?: string;
    last_name?: string;
    username?: string;
    product_title: string;
    amount: number | string;
    paid_at?: string;
  }>;
  count: number;
  page: number;
  pageSize: number;
  commission?: number;
  commissionPercent?: number;
  net?: number;
}

export interface RealtimeUpdate {
  table?: string;
  action?: string;
  id?: number;
  userId?: number;
  direction?: string;
  readAt?: string | null;
}
