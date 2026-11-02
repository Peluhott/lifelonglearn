// where the FastAPI backend runs; override with VITE_API_URL in frontend/.env if it moves
export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// Send the student's prompt to the tutor graph and call onEvent(event, data) for every
// Server-Sent Event it streams back (session, intake, plan, lessons, review, done, error).
// We use fetch instead of EventSource because EventSource can only make GET requests.
export async function streamTutor(prompt, onEvent) {
  const response = await fetch(`${API_URL}/tutor/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
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

async function getJson(path) {
  const response = await fetch(`${API_URL}${path}`)
  if (!response.ok) throw new Error(`Request failed: ${response.status}`)
  return response.json()
}

// past sessions for the sidebar, newest first: [{ id, title, created_at }]
export const listSessions = () => getJson('/sessions')

// one saved session: { id, prompt, plan, lessons, review }
export const getSession = (id) => getJson(`/sessions/${id}`)
