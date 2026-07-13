import { useState } from 'react'
import { Button } from 'antd'
import { LikeOutlined, DislikeOutlined, LikeFilled, DislikeFilled } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage, Citation } from '@/api/chat'

interface Props {
  msg: ChatMessage
  streaming?: boolean
  onFeedback?: (messageId: number, fb: 'up' | 'down') => void
}

function CitationPanel({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="cite-panel">
      <button className="cite-toggle" onClick={() => setOpen(!open)}>
        📎 引用来源（{citations.length} 条）{open ? '▲' : '▼'}
      </button>
      {open && (
        <div className="cite-list">
          {citations.map((c) => (
            <div key={c.index} className="cite-card">
              <div className="cite-meta">
                <span className="cite-idx">{c.index}</span>
                <span className="cite-type">{c.doc_type}</span>
                <span className="cite-loc">{c.source} · p{c.page_no}</span>
              </div>
              <div className="cite-snippet">{c.snippet}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function MessageBubble({ msg, streaming, onFeedback }: Props) {
  const isUser = msg.role === 'user'
  return (
    <div className={`msg-row ${isUser ? 'msg-user' : 'msg-bot'}`}>
      <div className={`msg-avatar ${isUser ? 'avatar-user' : 'avatar-bot'}`}>
        {isUser ? '👤' : '🤖'}
      </div>
      <div className="msg-body">
        <div className={`msg-bubble ${isUser ? 'bubble-user' : 'bubble-bot'}`}>
          {isUser ? (
            <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
          ) : streaming && !msg.content ? (
            <span className="typing-dots"><i>.</i><i>.</i><i>.</i></span>
          ) : (
            <div className="markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {msg.content}
              </ReactMarkdown>
              {streaming && <span className="typing-cursor" />}
            </div>
          )}
          {!isUser && msg.citations && msg.citations.length > 0 && (
            <CitationPanel citations={msg.citations} />
          )}
        </div>
        {!isUser && !streaming && msg.id > 0 && onFeedback && (
          <div className="msg-feedback">
            <Button
              type="text" size="small"
              icon={msg.feedback === 'up' ? <LikeFilled /> : <LikeOutlined />}
              onClick={() => onFeedback(msg.id, 'up')}
            />
            <Button
              type="text" size="small"
              icon={msg.feedback === 'down' ? <DislikeFilled /> : <DislikeOutlined />}
              onClick={() => onFeedback(msg.id, 'down')}
            />
          </div>
        )}
      </div>
    </div>
  )
}
