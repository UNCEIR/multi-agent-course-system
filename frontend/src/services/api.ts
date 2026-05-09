import type { Product, RecommendationResponse, Order, ChatMessage } from '../types'

const API_BASE = '/api/v1'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  getProducts: (params?: { category?: string; search?: string; page?: number; size?: number }) => {
    const qs = new URLSearchParams()
    if (params?.category) qs.set('category', params.category)
    if (params?.search) qs.set('search', params.search)
    if (params?.page) qs.set('page', String(params.page))
    if (params?.size) qs.set('size', String(params.size))
    return request<{ items: Product[]; total: number }>(`/products?${qs}`)
  },

  getProduct: (id: string) =>
    request<Product>(`/products/${id}`),

  getRecommendations: (body: { user_id: string; scene: string; num_items: number; context: Record<string, unknown> }) =>
    request<RecommendationResponse>('/recommend', { method: 'POST', body: JSON.stringify(body) }),

  getOrders: (userId: string) =>
    request<Order[]>(`/orders?user_id=${userId}`),

  getOrder: (orderId: string) =>
    request<Order>(`/orders/${orderId}`),

  createOrder: (body: { user_id: string; items: { product_id: string; quantity: number }[]; shipping_address: string }) =>
    request<Order>('/orders', { method: 'POST', body: JSON.stringify(body) }),

  chatbot: (messages: ChatMessage[]) =>
    request<{ message: string; products?: Product[] }>('/chatbot', {
      method: 'POST',
      body: JSON.stringify({ messages }),
    }),
}
