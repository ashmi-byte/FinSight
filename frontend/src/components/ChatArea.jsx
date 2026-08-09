import { useState, useRef, useEffect } from 'react'
import ReasoningPanel from './ReasoningPanel'
import './ChatArea.css'

export default function ChatArea() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef()

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async () => {
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    setLoading(true)

    // Add user message
    setMessages(prev => [...prev, { role: 'user', text: q }])

    // Add empty assistant message that we'll fill via SSE
    const assistantId = Date.now()
    setMessages(prev => [...prev, {
      id: assistantId,
      role: 'assistant',
      steps: [],
      answer: null,
      sources: [],
    }])

    const res = await fetch('http://localhost:8000/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q }),
    })

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const parts = buffer.split('\n\n')
      buffer = parts.pop()

      for (const part of parts) {
        const lines = part.trim().split('\n')
        const eventLine = lines.find(l => l.startsWith('event:'))
        const dataLine  = lines.find(l => l.startsWith('data:'))
        if (!eventLine || !dataLine) continue

        const event = eventLine.replace('event:', '').trim()
        const data  = JSON.parse(dataLine.replace('data:', '').trim())

        setMessages(prev => prev.map(m => {
          if (m.id !== assistantId) return m
          if (event === 'answer') {
            return { ...m, answer: data.answer, sources: data.sources, steps: [...m.steps] }
          }
          return { ...m, steps: [...m.steps, { event, data }] }
        }))
      }
    }

    setLoading(false)
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  return (
    <div className="chat-area">
      <div className="messages">
        {messages.length === 0 && (
          <div className="welcome">
            <div className="welcome-title">Financial Report Q&A</div>
            <div className="welcome-sub">Ask questions about uploaded earnings reports</div>
            <div className="examples">
              <div className="example-chip" onClick={() => setInput("What was Google's total revenue in 2024?")}>
                What was Google's total revenue in 2024?
              </div>
              <div className="example-chip" onClick={() => setInput("Why did Google's revenue grow from 2024 to 2025?")}>
                Why did Google's revenue grow from 2024 to 2025?
              </div>
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`message message-${m.role}`}>
            {m.role === 'user' ? (
              <div className="bubble user-bubble">{m.text}</div>
            ) : (
              <div className="assistant-message">
                <ReasoningPanel steps={m.steps} isComplete={!!m.answer} />
                {m.answer && (
                  <div className="answer-bubble">
                    <div className="answer-text">{m.answer}</div>
                    {m.sources?.length > 0 && (
                      <div className="sources">
                        Sources: {m.sources.join(' · ')}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        <div ref={bottomRef} />
      </div>

      <div className="input-area">
        <textarea
          className="input-box"
          placeholder="Ask a question about the financial reports..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          rows={2}
          disabled={loading}
        />
        <button className="send-btn" onClick={sendMessage} disabled={loading || !input.trim()}>
          {loading ? '...' : '↑'}
        </button>
      </div>
    </div>
  )
}
