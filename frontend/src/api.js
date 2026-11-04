// where the FastAPI backend runs; override with VITE_API_URL in frontend/.env if it moves
export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// POST to the tutor and call onEvent(event, data) for every Server-Sent Event it streams back
// (session, intake, plan, lessons, review, question, wrap_up, done, error).
// We use fetch instead of EventSource because EventSource can only make GET requests.
async function postStream(path, body, onEvent) {
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

// start a new session from the student's prompt
export const streamTutor = (prompt, onEvent) => postStream('/tutor/stream', { prompt }, onEvent)

// continue a paused session with the student's answer
export const answerTutor = (id, answer, onEvent) => postStream(`/sessions/${id}/answer`, { answer }, onEvent)

async function getJson(path) {
  const response = await fetch(`${API_URL}${path}`)
  if (!response.ok) throw new Error(`Request failed: ${response.status}`)
  return response.json()
}

// past sessions for the sidebar, newest first: [{ id, title, created_at }]
export const listSessions = () => getJson('/sessions')

// one saved session: { id, prompt, method, plan, lessons, review, socratic, in_progress }
export const getSession = (id) => getJson(`/sessions/${id}`)
