// where the FastAPI backend runs; override with VITE_API_URL in frontend/.env if it moves
export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// Start a lesson: events session, intake, then plan, lessons, quiz for a structured lesson (the graph then waits for
// answers) or question for a Socratic dialogue, done / error.
export const streamTutor = (prompt, onEvent) => streamEvents('/tutor/stream', { prompt }, onEvent)

// Answer the waiting quiz (one picked choice per question, in order):
// events grade, then reteach + the next quiz if anything was missed, done / error.
export const submitAnswers = (sessionId, answers, onEvent) =>
  streamEvents(`/sessions/${sessionId}/answers`, { answers }, onEvent)

// Answer the waiting Socratic question: events question, or wrap_up when the dialogue ends, done / error.
export const answerTutor = (sessionId, answer, onEvent) =>
  streamEvents(`/sessions/${sessionId}/answer`, { answer }, onEvent)

// Retry a run that failed after grading (the session's `stalled` flag); streams like submitAnswers.
export const resumeSession = (sessionId, onEvent) => streamEvents(`/sessions/${sessionId}/resume`, {}, onEvent)

// POST and call onEvent(event, data) for every Server-Sent Event the API streams back.
// We use fetch instead of EventSource because EventSource can only make GET requests.
async function streamEvents(path, body, onEvent) {
  const response = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error(`Request failed: ${response.status}`)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // each event ends with a blank line; keep any half-received event in the buffer
    const frames = buffer.split('\n\n')
    buffer = frames.pop()

    for (const frame of frames) {
      let event = 'message'
      let data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7)
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (data) onEvent(event, JSON.parse(data))
    }
  }
}

async function request(path, options) {
  const response = await fetch(`${API_URL}${path}`, options)
  if (!response.ok) throw new Error(`Request failed: ${response.status}`)
  return response
}

const getJson = async (path) => (await request(path)).json()

// past sessions for the sidebar, newest first: [{ id, title, created_at }]
export const listSessions = () => getJson('/sessions')

// one saved session: { id, prompt, method, plan, lessons, followups, rounds: [{ grade, reteach }], waiting, stalled,
// socratic, in_progress }
export const getSession = (id) => getJson(`/sessions/${id}`)

export const deleteSession = (id) => request(`/sessions/${id}`, { method: 'DELETE' })

// a follow-up question about one lesson step (0-based index): { index, question, answer }
export const askAboutStep = async (sessionId, index, question) =>
  (
    await request(`/sessions/${sessionId}/steps/${index}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })
  ).json()
