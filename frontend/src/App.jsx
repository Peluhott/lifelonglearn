import { useEffect, useRef, useState } from 'react'
import {
  answerTutor,
  API_URL,
  askAboutStep,
  deleteSession,
  getSession,
  listSessions,
  resumeSession,
  streamTutor,
  submitAnswers,
} from './api.js'
import './App.css'

const ERROR_TEXT = 'Something went wrong. Please try again.'

// what a text check found: the gaps, or that there weren't any
const checkMessage = ({ passed, gaps }) => ({
  role: 'assistant',
  kind: 'text',
  content: passed ? 'Nice work, you covered it all.' : `Worth another look:\n${gaps.map((gap) => `- ${gap}`).join('\n')}`,
})

const shortDate = (iso) => new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })

function App() {
  // every message is { role: 'user' | 'assistant', kind, ... } where kind decides how it's drawn
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [status, setStatus] = useState(null) // what the tutor is doing right now ("Planning…"), null when idle
  const [pendingQuiz, setPendingQuiz] = useState(null) // { round, questions } held back until the student clicks to continue
  const [pendingCheck, setPendingCheck] = useState(null) // a text check's prompt, held back the same way
  const [sessions, setSessions] = useState([]) // past sessions for the sidebar
  const [sessionId, setSessionId] = useState(null) // the session on screen, null for a new lesson
  const [inDialogue, setInDialogue] = useState(false) // a Socratic dialogue is under way, so a message answers it
  const [confirmingDelete, setConfirmingDelete] = useState(null) // id of the sidebar row asking "Delete?"
  const [page, setPage] = useState(0) // the lesson pager's page: 0 is the hook, 1..n are the steps
  const [asking, setAsking] = useState(null) // { index, question } waiting for an answer
  const [askFailed, setAskFailed] = useState(null) // step index whose last question failed
  const shownSession = useRef(null) // sessionId without waiting for a render, for answers that arrive late
  const lessonShowing = useRef(false) // a check's first prompt has to wait until the student has read the lesson
  const gradedThisRun = useRef(false) // an answer run that fails after grading leaves the graph stalled, not waiting
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
      lessonShowing.current = true
      addMessage({ role: 'assistant', kind: 'lesson', plan: data, lessons: null, followups: [] }) // lessons arrive later
      setStatus('Writing up the lessons…')
    } else if (event === 'lessons') {
      addLessons(data.lessons)
      setStatus('Generating questions…')
    } else if (event === 'quiz') {
      setPendingQuiz(data) // don't show yet: the last lesson or reteach page has a button that reveals it
    } else if (event === 'grade') {
      gradedThisRun.current = true
      setMessages((prev) => prev.map((m) => (m.kind === 'review' && m.round === data.round ? { ...m, grade: data } : m)))
      if (data.score < data.total) setStatus('Taking another look at what you missed…')
    } else if (event === 'reteach') {
      addMessage({ role: 'assistant', kind: 'reteach', steps: data.steps })
    } else if (event === 'analogy') {
      lessonShowing.current = true
      addMessage({ role: 'assistant', kind: 'analogy', lesson: data })
      setStatus('Getting your questions ready…')
    } else if (event === 'question') {
      if (lessonShowing.current) {
        setPendingCheck(data.question)
      } else {
        addMessage({ role: 'assistant', kind: 'text', content: data.question })
        setInDialogue(true)
      }
    } else if (event === 'wrap_up') {
      addMessage({ role: 'assistant', kind: 'text', content: data.text })
      setInDialogue(false)
    } else if (event === 'check_result') {
      setInDialogue(false)
      if (data.check_type !== 'quiz') addMessage(checkMessage(data)) // a quiz shows its own results
    } else if (event === 'reexplain') {
      addMessage({ role: 'assistant', kind: 'text', content: data.text })
    } else if (event === 'error') {
      // after grading, the graph is stuck between nodes and needs a resume, not new answers
      addMessage({ role: 'assistant', kind: 'text', content: ERROR_TEXT, error: true, retry: gradedThisRun.current })
    }
    // 'intake' and 'done' don't show anything; "Planning…" covers intake and finally clears the status
  }

  // stream an answer run (grade, then any reteach and next quiz) into the thread
  const runAnswers = async (start, startStatus) => {
    gradedThisRun.current = false
    setStatus(startStatus)
    try {
      await start(onEvent)
    } catch {
      addMessage({ role: 'assistant', kind: 'text', content: ERROR_TEXT, error: true, retry: gradedThisRun.current })
    } finally {
      setStatus(null)
    }
  }

  const submitQuiz = (picks) => {
    if (loading) return
    runAnswers((onEv) => submitAnswers(sessionId, picks, onEv), 'Checking your answers…')
  }

  const retryRun = () => {
    if (loading) return
    setMessages((prev) => prev.filter((m) => !m.retry))
    runAnswers((onEv) => resumeSession(sessionId, onEv), 'Taking another look at what you missed…')
  }

  const lesson = messages.find((m) => m.kind === 'lesson')
  const quizShowing = messages.some((m) => m.kind === 'review' || m.kind === 'reteach')
  // with a finished lesson on screen, the composer asks about the step being read
  const askMode = Boolean(sessionId && lesson?.lessons && !quizShowing)

  const clearPending = () => {
    setPendingQuiz(null)
    setPendingCheck(null)
    lessonShowing.current = false
  }

  const send = async () => {
    const text = draft.trim()
    if (!text || loading) return
    if (askMode) return askStep(page - 1, text)
    setDraft('')
    if (inDialogue) {
      addMessage({ role: 'user', kind: 'text', content: text })
      setStatus('Thinking…')
    } else {
      // outside a dialogue every new topic is its own saved session, so start from a clean screen
      setMessages([{ role: 'user', kind: 'text', content: text }])
      showSession(null)
      setStatus('Planning…')
      clearPending()
    }
    try {
      await (inDialogue ? answerTutor(sessionId, text, onEvent) : streamTutor(text, onEvent))
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
    clearPending()
    setInDialogue(false)
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

  // rebuild a saved session: the lesson until the first quiz is answered, then every graded round and reteach
  const openSession = async (id) => {
    if (loading || id === sessionId) return
    showSession(id)
    clearPending()
    setInDialogue(false)
    try {
      const saved = await getSession(id)
      const rebuilt = [{ role: 'user', kind: 'text', content: saved.prompt }]
      const addTurns = (turns) => {
        for (const turn of turns) {
          rebuilt.push({ role: turn.role === 'student' ? 'user' : 'assistant', kind: 'text', content: turn.text })
        }
      }
      const dialogue = { socratic: saved.socratic, worked_faded: saved.worked_faded }[saved.method]
      if (dialogue) {
        addTurns(dialogue)
        setMessages(rebuilt)
        setInDialogue(saved.in_progress) // an unfinished dialogue picks up where it left off
        return
      }

      // a text check that hasn't been answered yet waits behind the lesson, as it did the first time
      const checkHeld = saved.in_progress && saved.check_turns.length === 1
      const checkStarted = saved.check_turns.length > 0 && !checkHeld
      if (!saved.rounds.length && !checkStarted) {
        if (saved.analogy_bridging) {
          rebuilt.push({ role: 'assistant', kind: 'analogy', lesson: saved.analogy_bridging })
        } else if (saved.plan) {
          rebuilt.push({ role: 'assistant', kind: 'lesson', plan: saved.plan, lessons: saved.lessons, followups: saved.followups })
        }
      }
      if (checkHeld) {
        setPendingCheck(saved.check_turns[0].text)
        lessonShowing.current = true
      }
      if (checkStarted) {
        addTurns(saved.check_turns)
        setInDialogue(saved.in_progress)
      }
      for (const { grade, reteach } of saved.rounds) {
        // a graded answer carries its question and choices, so it can stand in for the question
        rebuilt.push({ role: 'assistant', kind: 'review', round: grade.round, questions: grade.answers, grade })
        if (reteach.steps.length) rebuilt.push({ role: 'assistant', kind: 'reteach', steps: reteach.steps })
      }
      if (saved.check_result && saved.check_result.check_type !== 'quiz') rebuilt.push(checkMessage(saved.check_result))
      if (saved.reexplain) rebuilt.push({ role: 'assistant', kind: 'text', content: saved.reexplain })
      if (saved.stalled && !checkStarted) rebuilt.push({ role: 'assistant', kind: 'text', content: ERROR_TEXT, error: true, retry: true })
      setMessages(rebuilt)
      setPendingQuiz(saved.waiting)
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

  // show the waiting quiz: the first one replaces the lesson, later rounds go below the reteach that led to them
  const showQuestions = () => {
    const quiz = { role: 'assistant', kind: 'review', round: pendingQuiz.round, questions: pendingQuiz.questions, grade: null }
    setMessages((prev) => {
      if (!['lesson', 'analogy'].includes(prev.at(-1)?.kind)) return [...prev, quiz]
      const lastUser = prev.findLastIndex((m) => m.role === 'user')
      return [...prev.slice(0, lastUser + 1), quiz]
    })
    setPendingQuiz(null)
  }

  // show the waiting text check; it replaces the lesson, so retrieval practice really is from memory
  const showCheck = () => {
    setMessages((prev) => {
      const lastUser = prev.findLastIndex((m) => m.role === 'user')
      return [...prev.slice(0, lastUser + 1), { role: 'assistant', kind: 'text', content: pendingCheck }]
    })
    setPendingCheck(null)
    lessonShowing.current = false
    setInDialogue(true)
  }

  const checkReady = pendingQuiz !== null || pendingCheck !== null
  const continueToCheck = pendingQuiz ? showQuestions : showCheck

  const quizzes = messages.filter((m) => m.kind === 'review')
  // finished: the last thing on screen is a graded quiz and nothing else is coming
  const finished = !loading && !pendingQuiz && messages.at(-1)?.kind === 'review' && messages.at(-1).grade

  const onPlanPage = askMode && page === 0
  const cantSend = loading || !draft.trim() || onPlanPage || quizShowing || asking !== null
  const placeholder = loading
    ? 'Type a message'
    : inDialogue
      ? 'Type your answer'
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
                    questionsReady={i === messages.length - 1 && checkReady}
                    onContinue={continueToCheck}
                  />
                ) : m.kind === 'analogy' ? (
                  <Analogy
                    key={`${sessionId}-${i}`}
                    lesson={m.lesson}
                    questionsReady={i === messages.length - 1 && checkReady}
                    onContinue={continueToCheck}
                  />
                ) : m.kind === 'review' ? (
                  <Quiz
                    key={`${sessionId}-${i}`}
                    round={m.round}
                    questions={m.questions}
                    grade={m.grade}
                    canSubmit={!loading && !m.grade}
                    onSubmit={submitQuiz}
                  />
                ) : m.kind === 'reteach' ? (
                  <Reteach
                    key={`${sessionId}-${i}`}
                    steps={m.steps}
                    questionsReady={i === messages.length - 1 && pendingQuiz !== null}
                    onContinue={showQuestions}
                  />
                ) : (
                  <Message key={`${sessionId}-${i}`} message={m} onRetry={retryRun} retryDisabled={loading} />
                ),
              )}

              {finished && <Summary quizzes={quizzes} />}

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

function Message({ message, onRetry, retryDisabled }) {
  if (message.role === 'user') {
    return <div className="msg msg-user">{message.content}</div>
  }

  return (
    <div className={`msg msg-tutor${message.error ? ' msg-error' : ''}`}>
      {message.content}
      {message.retry && (
        <button className="retry" onClick={onRetry} disabled={retryDisabled}>
          Try again
        </button>
      )}
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
        <span className="pager-count">{page === 0 ? 'Before we start' : `Step ${page} of ${plan.steps.length}`}</span>
        <Progress count={pages} current={page} />
      </div>

      {page === 0 ? (
        <div>{plan.hook || `Let's learn ${plan.concept_to_teach}.`}</div>
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

// an analogy lesson: the explanation, what maps to what, and where the comparison stops working
function Analogy({ lesson, questionsReady, onContinue }) {
  return (
    <div className="msg msg-tutor pager">
      <div className="lesson-title">Think of it like {lesson.analogy}</div>
      {lesson.explanation}
      <ul className="plan-steps">
        {lesson.mapping.map((pair) => (
          <li key={pair}>{pair}</li>
        ))}
      </ul>
      <div className="lesson-title">Where the analogy breaks down</div>
      {lesson.limits}
      <div className="pager-nav">
        <button className="pager-next" onClick={onContinue} disabled={!questionsReady}>
          Continue to questions →
        </button>
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

// one quiz round, one question at a time. Picks can change until "Check answers" sends them to the grader node;
// once its grade arrives the quiz locks and shows right / wrong for each question
function Quiz({ round, questions, grade, canSubmit, onSubmit }) {
  const [picks, setPicks] = useState({}) // question index -> the choice the student clicked
  const [current, setCurrent] = useState(0) // which question is on screen

  const results = grade?.answers // same order as questions
  const shownPicks = results ? Object.fromEntries(results.map((a, i) => [i, a.picked])) : picks
  const answered = Object.keys(shownPicks).length
  const q = questions[current]
  const result = results?.[current]
  const isLast = current === questions.length - 1

  return (
    <div className="msg msg-tutor pager">
      <div className="pager-top">
        <span className="pager-count">
          {round > 1 ? 'New questions · ' : ''}Question {current + 1} of {questions.length}
        </span>
        <Progress count={questions.length} current={current} />
      </div>

      <div className="question-text">{q.question}</div>

      <div className="choices">
        {q.choices.map((choice, j) => {
          const right = result && choice.trim() === result.correct_answer.trim()
          const wrong = result && choice === result.picked && !result.is_correct
          const picked = !result && choice === shownPicks[current]
          return (
            <button
              key={choice}
              className={`choice${right ? ' right' : ''}${wrong ? ' wrong' : ''}${picked ? ' picked' : ''}`}
              disabled={!canSubmit}
              onClick={() => setPicks((prev) => ({ ...prev, [current]: choice }))}
            >
              <span className="choice-key">{LETTERS[j]}</span>
              {choice}
            </button>
          )
        })}
      </div>

      {result && (
        <div className={`feedback ${result.is_correct ? 'right' : 'wrong'}`}>
          {result.is_correct ? (
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
        {isLast && !grade ? (
          <button
            className="pager-next"
            onClick={() => onSubmit(questions.map((_, i) => picks[i]))}
            disabled={!canSubmit || answered < questions.length}
          >
            Check answers
          </button>
        ) : (
          <button className="pager-next" onClick={() => setCurrent(current + 1)} disabled={isLast}>
            Next question →
          </button>
        )}
      </div>

      {grade ? (
        <div className="score">
          You got {grade.score} of {grade.total} right.
        </div>
      ) : (
        <div className="quiz-hint">
          {answered} of {questions.length} answered
        </div>
      )}
    </div>
  )
}

// another look at each missed step: what the wrong answer suggests they believe, then a new explanation;
// the last page moves on to the new questions
function Reteach({ steps, questionsReady, onContinue }) {
  const [page, setPage] = useState(0)
  const step = steps[page]
  const isLast = page === steps.length - 1

  return (
    <div className="msg msg-tutor pager">
      <div className="pager-top">
        <span className="pager-count">
          Another look · {page + 1} of {steps.length}
        </span>
        <Progress count={steps.length} current={page} />
      </div>

      <div>
        <div className="lesson-title">{step.step}</div>
        <div className="misconception">
          <strong>What might be tripping you up:</strong> {step.misconception}
        </div>
        {step.explanation}
      </div>

      <div className="pager-nav">
        <button className="pager-back" onClick={() => setPage(page - 1)} disabled={page === 0}>
          ← Back
        </button>
        {isLast ? (
          <button className="pager-next" onClick={onContinue} disabled={!questionsReady}>
            Try the new questions →
          </button>
        ) : (
          <button className="pager-next" onClick={() => setPage(page + 1)}>
            Next →
          </button>
        )}
      </div>
    </div>
  )
}

// end of the lesson: the first-try score, and any step still missed after its retries
function Summary({ quizzes }) {
  const latest = new Map() // step index -> its most recent graded answer
  for (const quiz of quizzes) for (const answer of quiz.grade.answers) latest.set(answer.index, answer)
  const shaky = [...latest.values()].filter((a) => !a.is_correct)
  const first = quizzes[0].grade

  return (
    <div className="msg msg-tutor summary">
      <div className="lesson-title">{shaky.length ? 'Lesson finished' : 'Every step checked out'}</div>
      <p>
        First try: {first.score} of {first.total} right.
        {quizzes.length > 1 && ` After another look, ${latest.size - shaky.length} of ${latest.size} steps are solid.`}
      </p>
      {shaky.length > 0 && (
        <>
          <strong>Still needs work</strong>
          <ul className="plan-steps">
            {shaky.map((a) => (
              <li key={a.index}>{a.step}</li>
            ))}
          </ul>
          <p>Start a new lesson on one of these to dig in further.</p>
        </>
      )}
    </div>
  )
}

export default App
