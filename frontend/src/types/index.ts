export interface Product {
  product_id: string
  name: string
  category: string
  price: number
  description: string
  brand: string
  seller_id: string
  stock: number
  tags: string[]
  score: number
  image_url: string
}

export interface CartItem {
  product: Product
  quantity: number
}

export interface UserProfile {
  user_id: string
  age?: number
  gender?: string
  city?: string
  segments: string[]
  preferred_categories: string[]
  price_range: [number, number]
  recent_views: string[]
  recent_purchases: string[]
  rfm_score: Record<string, number>
  real_time_tags: Record<string, unknown>
}

export interface MarketingCopy {
  product_id: string
  copy: string
}

export interface RecommendationRequest {
  user_id: string
  scene: string
  num_items: number
  context: Record<string, unknown>
}

export interface RecommendationResponse {
  request_id: string
  user_id: string
  products: Product[]
  marketing_copies: MarketingCopy[]
  experiment_group: string
  total_latency_ms: number
  timestamp: string
}

export interface OrderItem {
  product_id: string
  name: string
  price: number
  quantity: number
}

export interface Order {
  order_id: string
  user_id: string
  items: OrderItem[]
  total_amount: number
  status: 'pending' | 'paid' | 'shipped' | 'delivered' | 'cancelled'
  shipping_address: string
  created_at: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  products?: Product[]
  timestamp: number
}
