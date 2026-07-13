import client from './client'

export interface Conversation {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export interface Citation {
  index: number
  source: string
  page_no: number
  doc_type: string
  chunk_id: number
  snippet: string
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  citations: Citation[] | null
  feedback: 'up' | 'down' | null
  created_at: string
}

export const chatApi = {
  listConversations: () => client.get<Conversation[]>('/conversations'),

  createConversation: (title = '新会话') =>
    client.post<Conversation>('/conversations', { title }),

  getMessages: (id: number) =>
    client.get<ChatMessage[]>(`/conversations/${id}/messages`),

  renameConversation: (id: number, title: string) =>
    client.put<Conversation>(`/conversations/${id}/title`, { title }),

  deleteConversation: (id: number) => client.delete(`/conversations/${id}`),

  submitFeedback: (messageId: number, feedback: 'up' | 'down') =>
    client.post(`/messages/${messageId}/feedback`, { feedback }),
}

/** SSE 事件类型，对应后端 services/chat.py 产出的事件。 */
export type ChatEvent =
  | { event: 'citations'; data: Citation[] }
  | { event: 'token'; data: string }
  | { event: 'done'; message_id: number }
  | { event: 'error'; data: string }

/**
 * 发起流式问答。SSE 走 POST + JWT 头，EventSource 不支持自定义头，
 * 因此用 fetch + ReadableStream 手动按 `data: {...}\n\n` 解析。
 */
export async function streamChat(
  conversationId: number,
  question: string,
  onEvent: (evt: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('token')
  const resp = await fetch(`/api/chat/${conversationId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ question }),
    signal,
  })

  if (!resp.ok || !resp.body) {
    if (resp.status === 401) {
      localStorage.removeItem('token')
      location.href = '/login'
    }
    throw new Error(`问答请求失败: ${resp.status}`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // 按 SSE 空行分隔事件
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const line = raw.trim()
      if (!line.startsWith('data:')) continue
      const payload = line.slice(5).trim()
      if (!payload) continue
      try {
        onEvent(JSON.parse(payload) as ChatEvent)
      } catch {
        // 忽略无法解析的分片
      }
    }
  }
}
