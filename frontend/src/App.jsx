import { useEffect, useRef, useState } from 'react'
import { streamTutor } from './api.js'
import './App.css'

const ERROR_TEXT = 'Something went wrong. Please try again.'

function App() {
  // every message is { role: 'user' | 'assistant', kind, ... } where kind decides how it's drawn
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [status, setStatus] = useState(null) // what the tutor is doing right now ("Planning…"), null when idle
  const [pendingQuestions, setPendingQuestions] = useState(null) // review questions held back until the student clicks to continue
  const scrollRef = useRef(null)
  const textareaRef = useRef(null)
  const loading = status !== null

  // keep the newest message in view
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, status])

  // grow the textarea with its content (CSS caps it at 160px)
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [draft])

  const addMessage = (message) => setMessages((prev) => [...prev, message])

  // fill in the lessons on the lesson message the plan created
  const addLessons = (lessons) =>
    setMessages((prev) => {
      const at = prev.findLastIndex((m) => m.kind === 'lesson')
      return prev.map((m, i) => (i === at ? { ...m, lessons } : m))
    })

  // turn each event from the tutor graph into what the student sees
  const onEvent = (event, data) => {
    if (event === 'plan') {
      addMessage({ role: 'assistant', kind: 'lesson', plan: data, lessons: null }) // lessons arrive later
      setStatus('Writing up the lessons…')
    } else if (event === 'lessons') {
      addLessons(data.lessons)
      setStatus('Generating questions…')
    } else if (event === 'review') {
      setPendingQuestions(data.questions) // don't show yet, "Continue to questions" on the last step reveals them
    } else if (event === 'error') {
      addMessage({ role: 'assistant', kind: 'text', content: ERROR_TEXT, error: true })
    }
    // 'intake' and 'done' don't show anything; "Planning…" covers intake and finally clears the status
  }

  const send = async () => {
    const text = draft.trim()
    if (!text || loading) return
    addMessage({ role: 'user', kind: 'text', content: text })
    setDraft('')
    setStatus('Planning…')
    setPendingQuestions(null) // a new lesson replaces any questions that were never opened
    try {
      await streamTutor(text, onEvent) // each message starts a fresh lesson for now (the graph has no memory yet)
    } catch {
      addMessage({ role: 'assistant', kind: 'text', content: ERROR_TEXT, error: true })
    } finally {
      setStatus(null)
    }
  }

  // Enter sends, Shift+Enter adds a new line
  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  // swap this lesson's plan and lessons for the quiz: keep everything up to the student's last message
  const showQuestions = () => {
    setMessages((prev) => {
      const lastUser = prev.findLastIndex((m) => m.role === 'user')
      return [...prev.slice(0, lastUser + 1), { role: 'assistant', kind: 'review', questions: pendingQuestions }]
    })
    setPendingQuestions(null)
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

          {messages.map((m, i) =>
            m.kind === 'lesson' ? (
              <Lesson
                key={i}
                plan={m.plan}
                lessons={m.lessons}
                // only the newest lesson can move on to the questions that just came back
                questionsReady={i === messages.length - 1 && pendingQuestions !== null}
                onContinue={showQuestions}
              />
            ) : (
              <Message key={i} message={m} />
            ),
          )}

          {status && <div className="thinking">{status}</div>}
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
    return <Quiz questions={message.questions} />
  }

  return (
    <div className={`msg msg-tutor${message.error ? ' msg-error' : ''}`}>
      {message.content}
    </div>
  )
}

// one segment per page, filled up to the current one
function Progress({ count, current }) {
  return (
    <div className="progress" style={{ gridTemplateColumns: `repeat(${count}, 1fr)` }}>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className={`progress-seg${i <= current ? ' on' : ''}`} />
      ))}
    </div>
  )
}

// the plan, then each lesson step, one page at a time with Back / Next;
// the last step's button moves on to the questions
function Lesson({ plan, lessons, questionsReady, onContinue }) {
  const [page, setPage] = useState(0) // 0 is the plan, 1..n are the steps
  const pages = plan.steps.length + 1
  const isLast = page === pages - 1
  const lesson = page > 0 && lessons ? lessons[page - 1] : null

  return (
    <div className="msg msg-tutor pager">
      <div className="pager-top">
        <span className="pager-count">{page === 0 ? 'The plan' : `Step ${page} of ${plan.steps.length}`}</span>
        <Progress count={pages} current={page} />
      </div>

      {page === 0 ? (
        <div>
          Here's how we'll learn {plan.concept_to_teach}:
          <ol className="plan-steps">
            {plan.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>
      ) : (
        <div>
          <div className="lesson-title">{lesson.step}</div>
          {lesson.explanation}
        </div>
      )}

      <div className="pager-nav">
        <button className="pager-back" onClick={() => setPage(page - 1)} disabled={page === 0}>
          ← Back
        </button>
        {isLast ? (
          <button className="pager-next" onClick={onContinue} disabled={!questionsReady}>
            Continue to questions →
          </button>
        ) : (
          // the steps aren't readable until the lessons arrive
          <button className="pager-next" onClick={() => setPage(page + 1)} disabled={!lessons}>
            Next →
          </button>
        )}
      </div>
    </div>
  )
}

const LETTERS = ['A', 'B', 'C', 'D']

// trim so a stray space from the model doesn't make the right answer look wrong
const isCorrect = (choice, q) => choice.trim() === q.correct_answer.trim()

// the review questions as clickable multiple choice, one at a time with Back / Next;
// each question locks after the first pick
function Quiz({ questions }) {
  const [picks, setPicks] = useState({}) // question index -> the choice the student clicked
  const [current, setCurrent] = useState(0) // which question is on screen
  const answered = Object.keys(picks).length
  const score = questions.filter((q, i) => picks[i] !== undefined && isCorrect(picks[i], q)).length

  const q = questions[current]
  const pick = picks[current]
  const done = pick !== undefined
  const isLast = current === questions.length - 1

  return (
    <div className="msg msg-tutor pager">
      <div className="pager-top">
        <span className="pager-count">
          Question {current + 1} of {questions.length}
        </span>
        <Progress count={questions.length} current={current} />
      </div>

      <div className="question-text">{q.question}</div>

      <div className="choices">
        {q.choices.map((choice, j) => {
          const right = done && isCorrect(choice, q) // always reveal the right answer once they've picked
          const wrong = done && choice === pick && !isCorrect(choice, q)
          return (
            <button
              key={choice}
              className={`choice${right ? ' right' : ''}${wrong ? ' wrong' : ''}`}
              disabled={done}
              onClick={() => setPicks((prev) => ({ ...prev, [current]: choice }))}
            >
              <span className="choice-key">{LETTERS[j]}</span>
              {choice}
            </button>
          )
        })}
      </div>

      {done && (
        <div className={`feedback ${isCorrect(pick, q) ? 'right' : 'wrong'}`}>
          {isCorrect(pick, q) ? (
            <strong>Right.</strong>
          ) : (
            <>
              <strong>Not quite.</strong> The correct answer is highlighted in green.
            </>
          )}
        </div>
      )}

      <div className="pager-nav">
        <button className="pager-back" onClick={() => setCurrent(current - 1)} disabled={current === 0}>
          ← Back
        </button>
        <button className="pager-next" onClick={() => setCurrent(current + 1)} disabled={isLast}>
          Next question →
        </button>
      </div>

      {answered === questions.length && (
        <div className="score">
          You got {score} of {questions.length} right.
        </div>
      )}
    </div>
  )
}

export default App
