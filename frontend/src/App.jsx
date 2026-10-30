import { useEffect, useRef, useState } from 'react'
import { streamTutor } from './api.js'
import './App.css'

const ERROR_TEXT = 'Something went wrong. Please try again.'

function App() {
  // every message is { role: 'user' | 'assistant', kind, ... } where kind decides how it's drawn
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef(null)
  const textareaRef = useRef(null)

  // keep the newest message in view
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, loading])

  // grow the textarea with its content (CSS caps it at 160px)
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [draft])

  const addMessage = (message) => setMessages((prev) => [...prev, message])

  // turn each event from the tutor graph into a tutor message
  const onEvent = (event, data) => {
    if (event === 'plan') {
      const steps = data.steps.map((step, i) => `${i + 1}. ${step}`).join('\n')
      addMessage({ role: 'assistant', kind: 'text', content: `Here's how we'll learn ${data.concept_to_teach}:\n\n${steps}` })
    } else if (event === 'step') {
      addMessage({
        role: 'assistant',
        kind: 'text',
        label: `Step ${data.index + 1} of ${data.total} · ${data.step}`,
        content: data.explanation,
      })
    } else if (event === 'review') {
      addMessage({ role: 'assistant', kind: 'review', questions: data.questions })
    } else if (event === 'error') {
      addMessage({ role: 'assistant', kind: 'text', content: ERROR_TEXT, error: true })
    }
    // 'intake' and 'done' don't show anything; "Thinking…" covers intake and finally clears loading
  }

  const send = async () => {
    const text = draft.trim()
    if (!text || loading) return
    addMessage({ role: 'user', kind: 'text', content: text })
    setDraft('')
    setLoading(true)
    try {
      await streamTutor(text, onEvent) // each message starts a fresh lesson for now (the graph has no memory yet)
    } catch {
      addMessage({ role: 'assistant', kind: 'text', content: ERROR_TEXT, error: true })
    } finally {
      setLoading(false)
    }
  }

  // Enter sends, Shift+Enter adds a new line
  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const cantSend = loading || !draft.trim()

  return (
    <div className="app">
      <header className="header">
        <div className="logo" />
        <span className="wordmark">Lifelong</span>
      </header>

      <main className="messages" ref={scrollRef}>
        <div className="thread">
          {messages.length === 0 && (
            <div className="empty">
              <h1>What would you like to learn?</h1>
              <p>Ask a question or describe a topic, and your tutor will take it from there.</p>
            </div>
          )}

          {messages.map((m, i) => (
            <Message key={i} message={m} />
          ))}

          {loading && <div className="thinking">Thinking…</div>}
        </div>
      </main>

      <div className="composer-wrap">
        <div className="composer">
          <textarea
            ref={textareaRef}
            rows={1}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Type a message"
          />
          <button className="send" onClick={send} disabled={cantSend}>
            Send
          </button>
        </div>
      </div>
    </div>
  )
}

function Message({ message }) {
  if (message.role === 'user') {
    return <div className="msg msg-user">{message.content}</div>
  }

  if (message.kind === 'review') {
    return (
      <div className="msg msg-tutor">
        Check your understanding:
        {message.questions.map((q, i) => (
          <div className="question" key={i}>
            {i + 1}. {q.question}
            <ol>
              {q.choices.map((choice) => (
                <li key={choice}>{choice}</li>
              ))}
            </ol>
            <details>
              <summary>Show answer</summary>
              {q.correct_answer}
            </details>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className={`msg msg-tutor${message.error ? ' msg-error' : ''}`}>
      {message.label && <div className="msg-label">{message.label}</div>}
      {message.content}
    </div>
  )
}

export default App
