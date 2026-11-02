import { useEffect, useRef, useState } from 'react'
import { API_URL, askAboutStep, deleteSession, getSession, listSessions, streamTutor } from './api.js'
import './App.css'

const ERROR_TEXT = 'Something went wrong. Please try again.'

const shortDate = (iso) => new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

function App() {
  // every message is { role: 'user' | 'assistant', kind, ... } where kind decides how it's drawn
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [status, setStatus] = useState(null) // what the tutor is doing right now ("Planning…"), null when idle
  const [pendingQuestions, setPendingQuestions] = useState(null) // review questions held back until the student clicks to continue
  const [sessions, setSessions] = useState([]) // past sessions for the sidebar
  const [sessionId, setSessionId] = useState(null) // the session on screen, null for a new lesson
  const [confirmingDelete, setConfirmingDelete] = useState(null) // id of the sidebar row asking "Delete?"
  const [page, setPage] = useState(0) // the lesson pager's page: 0 is the plan, 1..n are the steps
  const [asking, setAsking] = useState(null) // { index, question } waiting for an answer
  const [askFailed, setAskFailed] = useState(null) // step index whose last question failed
  const shownSession = useRef(null) // sessionId without waiting for a render, for answers that arrive late
  const scrollRef = useRef(null)
  const textareaRef = useRef(null)
  const loading = status !== null

  // every switch of what's on screen goes through here, so the pager and any pending question start over
  const showSession = (id) => {
    shownSession.current = id
    setSessionId(id)
    setPage(0)
    setAsking(null)
    setAskFailed(null)
  }

  const refreshSessions = () =>
    listSessions()
      .then(setSessions)
      .catch(() => {}) // the sidebar is optional; the tutor still works without it

  useEffect(() => {
    refreshSessions()
  }, [])

  // a click anywhere except the red Delete button cancels it
  useEffect(() => {
    if (!confirmingDelete) return
    const cancel = (e) => {
      if (!e.target.closest('.session-delete.confirm')) setConfirmingDelete(null)
    }
    document.addEventListener('mousedown', cancel)
    return () => document.removeEventListener('mousedown', cancel)
  }, [confirmingDelete])

  // keep the newest message in view
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, status, asking])

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
    if (event === 'session') {
      showSession(data.id)
    } else if (event === 'plan') {
      addMessage({ role: 'assistant', kind: 'lesson', plan: data, lessons: null, followups: [] }) // lessons arrive later
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

  const lesson = messages.find((m) => m.kind === 'lesson')
  const quizShowing = messages.some((m) => m.kind === 'review')
  // with a finished lesson on screen, the composer asks about the step being read
  const askMode = Boolean(sessionId && lesson?.lessons && !quizShowing)

  const send = async () => {
    const text = draft.trim()
    if (!text || loading) return
    if (askMode) return askStep(page - 1, text)
    // every new topic is its own saved session, so start from a clean screen
    setMessages([{ role: 'user', kind: 'text', content: text }])
    showSession(null)
    setDraft('')
    setStatus('Planning…')
    setPendingQuestions(null)
    try {
      await streamTutor(text, onEvent)
    } catch {
      addMessage({ role: 'assistant', kind: 'text', content: ERROR_TEXT, error: true })
    } finally {
      setStatus(null)
      refreshSessions()
    }
  }

  const newLesson = () => {
    if (loading) return
    setMessages([])
    showSession(null)
    setPendingQuestions(null)
  }

  const removeSession = async (id) => {
    setConfirmingDelete(null)
    try {
      await deleteSession(id)
    } catch {
      return refreshSessions() // it may already be gone; show what the server has
    }
    setSessions((prev) => prev.filter((s) => s.id !== id))
    if (id === sessionId) newLesson()
  }

  // answer a question about one step (0-based) and show it under that step; the pager stays where it is
  const askStep = async (index, question) => {
    if (index < 0 || asking) return
    const id = sessionId
    setDraft('')
    setAsking({ index, question })
    setAskFailed(null)
    try {
      const followup = await askAboutStep(id, index, question)
      if (shownSession.current !== id) return // the student opened another lesson while waiting
      setMessages((prev) =>
        prev.map((m) => (m.kind === 'lesson' ? { ...m, followups: [...m.followups, followup] } : m)),
      )
      setAsking(null)
    } catch {
      if (shownSession.current !== id) return
      setDraft((current) => current || question) // give the question back so it can be sent again
      setAskFailed(index)
      setAsking(null)
    }
  }

  // rebuild a saved session the way it looked when its lessons finished (the quiz starts fresh)
  const openSession = async (id) => {
    if (loading || id === sessionId) return
    showSession(id)
    setPendingQuestions(null)
    try {
      const saved = await getSession(id)
      setMessages([
        { role: 'user', kind: 'text', content: saved.prompt },
        ...(saved.plan ? [{ role: 'assistant', kind: 'lesson', plan: saved.plan, lessons: saved.lessons, followups: saved.followups ?? [] }] : []),
      ])
      setPendingQuestions(saved.review ? saved.review.questions : null)
    } catch {
      setMessages([{ role: 'assistant', kind: 'text', content: "Couldn't open that lesson.", error: true }])
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

  const onPlanPage = askMode && page === 0
  const cantSend = loading || !draft.trim() || onPlanPage || quizShowing || asking !== null
  const placeholder = loading
    ? 'Type a message'
    : quizShowing
      ? 'Quiz time. Use + New lesson to learn something else'
      : onPlanPage
        ? 'Click Next to start, then ask about any step'
        : askMode
          ? `Ask about step ${page}…`
          : 'What would you like to learn?'

  return (
    <div className="app">
      <header className="header">
        <div className="logo" />
        <span className="wordmark">Lifelong</span>
      </header>

      <div className="body">
        <aside className="sidebar">
          <button className="new-lesson" onClick={newLesson} disabled={loading}>
            + New lesson
          </button>
          <nav className="session-list">
            {sessions.map((s) => {
              const confirming = confirmingDelete === s.id
              return (
                <div key={s.id} className={`session${s.id === sessionId ? ' on' : ''}${confirming ? ' confirming' : ''}`}>
                  <button className="session-open" onClick={() => openSession(s.id)} disabled={loading}>
                    <span className="session-title">{s.title}</span>
                    <span className="session-date">{shortDate(s.created_at)}</span>
                  </button>
                  <button
                    className={`session-delete${confirming ? ' confirm' : ''}`}
                    onClick={() => (confirming ? removeSession(s.id) : setConfirmingDelete(s.id))}
                    disabled={loading}
                    aria-label={confirming ? `Confirm deleting ${s.title}` : `Delete ${s.title}`}
                    title={confirming ? undefined : 'Delete lesson'}
                  >
                    {confirming ? 'Delete' : '×'}
                  </button>
                </div>
              )
            })}
          </nav>
        </aside>

        <div className="chat">
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
                    key={`${sessionId}-${i}`} // a different session gets a fresh pager instead of keeping the old page
                    plan={m.plan}
                    lessons={m.lessons}
                    followups={m.followups}
                    page={page}
                    setPage={setPage}
                    asking={asking}
                    askFailed={askFailed}
                    // only the newest lesson can move on to the questions that just came back
                    questionsReady={i === messages.length - 1 && pendingQuestions !== null}
                    onContinue={showQuestions}
                  />
                ) : (
                  <Message key={`${sessionId}-${i}`} message={m} />
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
                placeholder={placeholder}
                disabled={onPlanPage || quizShowing}
              />
              <button className="send" onClick={send} disabled={cantSend}>
                Send
              </button>
            </div>
          </div>
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
function Lesson({ plan, lessons, followups, page, setPage, asking, askFailed, questionsReady, onContinue }) {
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
          {/* only steps where the teacher asked for a picture have one */}
          {lesson.image_url && <img className="lesson-image" src={API_URL + lesson.image_url} alt={lesson.image_prompt} />}
          <StepQuestions
            followups={followups.filter((f) => f.index === page - 1)}
            asking={asking?.index === page - 1 ? asking.question : null}
            failed={askFailed === page - 1}
          />
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

// the student's questions about one step (asked in the composer) with the tutor's answers
function StepQuestions({ followups, asking, failed }) {
  if (!followups.length && !asking && !failed) return null

  return (
    <div className="step-questions">
      {followups.map((f, i) => (
        <div key={i} className="followup">
          <div className="followup-q">{f.question}</div>
          <div className="followup-a">{f.answer}</div>
        </div>
      ))}
      {asking && (
        <div className="followup">
          <div className="followup-q">{asking}</div>
          <div className="followup-a thinking">Thinking…</div>
        </div>
      )}
      {failed && <div className="msg-error ask-error">Couldn't get an answer. Please try again.</div>}
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
