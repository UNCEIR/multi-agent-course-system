import { create } from 'zustand'
import type { Product, CartItem, ChatMessage } from '../types'

interface CartStore {
  items: CartItem[]
  addItem: (product: Product, quantity?: number) => void
  removeItem: (productId: string) => void
  updateQuantity: (productId: string, quantity: number) => void
  clearCart: () => void
  totalAmount: () => number
  totalItems: () => number
}

export const useCartStore = create<CartStore>((set, get) => ({
  items: [],
  addItem: (product, quantity = 1) =>
    set((state) => {
      const existing = state.items.find((i) => i.product.product_id === product.product_id)
      if (existing) {
        return {
          items: state.items.map((i) =>
            i.product.product_id === product.product_id
              ? { ...i, quantity: i.quantity + quantity }
              : i
          ),
        }
      }
      return { items: [...state.items, { product, quantity }] }
    }),
  removeItem: (productId) =>
    set((state) => ({ items: state.items.filter((i) => i.product.product_id !== productId) })),
  updateQuantity: (productId, quantity) =>
    set((state) => ({
      items: quantity <= 0
        ? state.items.filter((i) => i.product.product_id !== productId)
        : state.items.map((i) =>
            i.product.product_id === productId ? { ...i, quantity } : i
          ),
    })),
  clearCart: () => set({ items: [] }),
  totalAmount: () => get().items.reduce((sum, i) => sum + i.product.price * i.quantity, 0),
  totalItems: () => get().items.reduce((sum, i) => sum + i.quantity, 0),
}))

interface ChatbotStore {
  isOpen: boolean
  messages: ChatMessage[]
  toggle: () => void
  addMessage: (msg: ChatMessage) => void
}

export const useChatbotStore = create<ChatbotStore>((set) => ({
  isOpen: false,
  messages: [
    {
      id: '0',
      role: 'assistant',
      content: 'Hi! I\'m your AI shopping assistant. I can help you find products, check stock, place orders, and give personalized recommendations. What can I help with today?',
      timestamp: Date.now(),
    },
  ],
  toggle: () => set((s) => ({ isOpen: !s.isOpen })),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
}))
