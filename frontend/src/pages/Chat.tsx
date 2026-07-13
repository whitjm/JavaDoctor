import { useEffect, useRef, useState, useCallback } from 'react'
import { Button, Input, Empty, Spin, message as antMessage } from 'antd'
import { SendOutlined, PlusOutlined, SettingOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import {
  chatApi, streamChat, type Conversation, type ChatMessage,
} from '@/api/chat'
import MessageBubble from '@/components/MessageBubble'

export default function ChatPage() {
  const navigate = useNavigate()
  const { user, logout, isAdmin } = useAuthStore()

  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [loadingMsgs, setLoadingMsgs] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const sendingConvRef = useRef<number | null>(null)

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      const el = scrollRef.current
      if (el) el.scrollTop = el.scrollHeight
    })
  }, [])

  const loadConversations = useCallback(async () => {
    try {
      const { data } = await chatApi.listConversations()
      setConversations(data)
      return data
    } catch { return [] }
  }, [])

  useEffect(() => {
    loadConversations().then((list) => {
      if (list.length > 0 && activeId == null) setActiveId(list[0].id)
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 切换会话 → 拉历史
  useEffect(() => {
    if (activeId == null) { setMessages([]); return }
    if (activeId < 0) { setMessages([]); return }
    if (sendingConvRef.current === activeId) return
    setLoadingMsgs(true)
    chatApi
      .getMessages(activeId)
      .then(({ data }) => setMessages(data))
      .finally(() => { setLoadingMsgs(false); scrollToBottom() })
  }, [activeId, scrollToBottom])

  // 新建：立刻清屏，不等后端
  const onNewConversation = () => {
    if (sending) return
    setActiveId(null)
    setMessages([])
  }

  // 删除：立刻移除 UI，后台删后端，失败则回滚
  const onDeleteConversation = (id: number) => {
    const prev = conversations
    setConversations(prev.filter((c) => c.id !== id))
    if (activeId === id) setActiveId(null)
    if (id < 0) return
    chatApi.deleteConversation(id).catch(() => {
      antMessage.error('删除失败')
      setConversations(prev)
    })
  }

  const onFeedback = async (messageId: number, fb: 'up' | 'down') => {
    try {
      await chatApi.submitFeedback(messageId, fb)
      setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId ? { ...m, feedback: m.feedback === fb ? null : fb } : m,
        ),
      )
    } catch { /* already toasted */ }
  }

  const onSend = async () => {
    const question = input.trim()
    if (!question || sending) return

    // 立刻动界面：思考中占位秒现
    setInput('')
    setSending(true)
    const userMsg: ChatMessage = { id: -Date.now(), role: 'user', content: question, citations: null, feedback: null, created_at: new Date().toISOString() }
    const asstMsg: ChatMessage = { id: 0, role: 'assistant', content: '', citations: null, feedback: null, created_at: new Date().toISOString() }
    setMessages((prev) => [...prev, userMsg, asstMsg])
    scrollToBottom()

    const controller = new AbortController()
    abortRef.current = controller

    try {
      let convId = activeId
      if (convId == null || convId < 0) {
        const { data } = await chatApi.createConversation()
        setConversations((prev) => [data, ...prev])
        convId = data.id
        setActiveId(convId)
      }
      sendingConvRef.current = convId

      await streamChat(convId, question, (evt) => {
        if (evt.event === 'citations') {
          setMessages((prev) => { const next = [...prev]; next[next.length - 1] = { ...next[next.length - 1], citations: evt.data }; return next })
        } else if (evt.event === 'token') {
          setMessages((prev) => { const next = [...prev]; const last = next[next.length - 1]; next[next.length - 1] = { ...last, content: last.content + evt.data }; return next })
          scrollToBottom()
        } else if (evt.event === 'done') {
          setMessages((prev) => { const next = [...prev]; next[next.length - 1] = { ...next[next.length - 1], id: evt.message_id }; return next })
        } else if (evt.event === 'error') {
          antMessage.error(evt.data)
        }
      }, controller.signal)
      loadConversations()
    } catch (e) {
      if (!controller.signal.aborted) {
        antMessage.error('问答失败')
        setMessages((prev) => prev.slice(0, -2))
        setInput(question)
      }
    } finally {
      setSending(false)
      sendingConvRef.current = null
      abortRef.current = null
    }
  }

  const onLogout = async () => {
    abortRef.current?.abort()
    await logout()
    navigate('/login')
  }

  return (
    <div className="chat-page">
      {/* 侧栏 */}
      <aside className={`chat-sidebar ${sidebarOpen ? '' : 'collapsed'}`}>
        <div className="sidebar-top">
          <h2 className="sidebar-logo">JavaDoctor</h2>
          <button className="sidebar-toggle" onClick={() => setSidebarOpen(false)} title="收起侧栏">‹</button>
        </div>
        <button className="new-chat-btn" onClick={onNewConversation} disabled={sending}>
          <PlusOutlined /> 新对话
        </button>
        <div className="conv-list">
          {conversations.length === 0 ? (
            <div className="conv-empty">暂无对话</div>
          ) : (
            conversations.map((c) => (
              <div
                key={c.id}
                className={`conv-item ${c.id === activeId ? 'active' : ''}`}
                onClick={() => setActiveId(c.id)}
              >
                <span className="conv-title">{c.title}</span>
                <button
                  className="conv-del"
                  title="删除"
                  onClick={(e) => { e.stopPropagation(); onDeleteConversation(c.id) }}
                >×</button>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* 折叠态展开按钮 */}
      {!sidebarOpen && (
        <button className="sidebar-expand" onClick={() => setSidebarOpen(true)} title="展开侧栏">
          <span style={{ fontSize: 18 }}>›</span>
        </button>
      )}

      {/* 主区域 */}
      <main className="chat-main">
        <div className="chat-topbar">
          <span className="model-badge">qwen3.5:4b</span>
          <div className="topbar-right">
            <span className="topbar-user">{user?.username}</span>
            {isAdmin() && (
              <Button size="small" icon={<SettingOutlined />} onClick={() => navigate('/admin')}>管理</Button>
            )}
            <Button size="small" onClick={onLogout}>退出</Button>
          </div>
        </div>

        <div className="chat-messages" ref={scrollRef}>
          {loadingMsgs ? (
            <div style={{ textAlign: 'center', marginTop: 60 }}><Spin /></div>
          ) : messages.length === 0 ? (
            <Empty description="开始你的第一个 Java 面试问题吧" style={{ marginTop: 80 }} />
          ) : (
            messages.map((m, i) => (
              <MessageBubble
                key={m.id !== 0 ? m.id : `s-${i}`}
                msg={m}
                streaming={sending && i === messages.length - 1 && m.role === 'assistant'}
                onFeedback={onFeedback}
              />
            ))
          )}
        </div>

        <div className="chat-input-bar">
          <Input.TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入 Java 面试问题，Enter 发送，Shift+Enter 换行"
            autoSize={{ minRows: 1, maxRows: 4 }}
            onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); onSend() } }}
            disabled={sending}
            style={{ borderRadius: 10 }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={sending}
            onClick={onSend}
            style={{ borderRadius: 10, height: 42, minWidth: 60, marginLeft: 8 }}
          />
        </div>
      </main>
    </div>
  )
}
