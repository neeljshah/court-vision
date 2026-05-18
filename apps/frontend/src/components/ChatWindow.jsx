import { useState, useRef, useEffect } from 'react'
import { initialChatHistory, getMockResponse } from '../mockData'

// TODO: Replace getMockResponse with real Claude API calls (Phase 15)
// Integration point: POST /api/chat with { message, tools: ['get_prediction', 'get_props', 'render_chart'] }
// Claude model: claude-sonnet-4-6

// Minimal markdown renderer for bold/italic/tables/bullets
function renderMarkdown(text) {
  const lines = text.split('\n')
  const elements = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Table detection (line contains |)
    if (line.includes('|') && i + 1 < lines.length && lines[i + 1].includes('---')) {
      const rows = []
      rows.push(line)
      i += 2 // skip separator
      while (i < lines.length && lines[i].includes('|')) {
        rows.push(lines[i]); i++
      }
      const headers = rows[0].split('|').filter(Boolean).map(h => h.trim())
      elements.push(
        <div key={i} className="overflow-x-auto my-2">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr>{headers.map(h => <th key={h} className="text-left text-gray-400 border-b border-gray-700 pb-1 pr-4 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody>
              {rows.slice(1).map((row, ri) => (
                <tr key={ri}>
                  {row.split('|').filter(Boolean).map((cell, ci) => (
                    <td key={ci} className="text-gray-300 py-0.5 pr-4">{cell.trim()}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
      continue
    }

    // Bullet points
    if (line.startsWith('• ') || line.startsWith('* ')) {
      elements.push(
        <div key={i} className="flex gap-2 text-sm text-gray-300 leading-relaxed">
          <span className="text-orange-500 shrink-0 mt-0.5">•</span>
          <span dangerouslySetInnerHTML={{ __html: formatInline(line.slice(2)) }} />
        </div>
      )
      i++; continue
    }

    // Emoji-prefixed lines (like 🟢 picks)
    if (/^[🟢🟡🔴⚠️]/.test(line)) {
      elements.push(
        <div key={i} className="text-sm text-gray-200 leading-relaxed"
          dangerouslySetInnerHTML={{ __html: formatInline(line) }} />
      )
      i++; continue
    }

    // Empty line = paragraph break
    if (line.trim() === '') {
      elements.push(<div key={i} className="h-1" />)
      i++; continue
    }

    // Default text line
    elements.push(
      <p key={i} className="text-sm text-gray-300 leading-relaxed"
        dangerouslySetInnerHTML={{ __html: formatInline(line) }} />
    )
    i++
  }
  return <div className="space-y-1">{elements}</div>
}

function formatInline(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-white font-semibold">$1</strong>')
    .replace(/\*(.+?)\*/g, '<em class="text-gray-300 italic">$1</em>')
    .replace(/`(.+?)`/g, '<code class="font-mono text-orange-300 bg-orange-500/10 px-1 rounded text-xs">$1</code>')
}

const SUGGESTED_QUERIES = [
  "What's the edge on tonight's DEN vs LAL?",
  "LeBron points prop analysis",
  "Best bets tonight — show all edges",
  "Jayson Tatum projection vs MIA",
  "How accurate is the win probability model?",
]

export default function ChatWindow({ user }) {
  const [messages, setMessages] = useState(initialChatHistory)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function sendMessage(text) {
    const trimmed = (text || input).trim()
    if (!trimmed || loading) return

    const userMsg = {
      id: Date.now(),
      role: 'user',
      text: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    // TODO: Replace with Claude API call (Phase 15)
    // fetch('/api/chat', { method: 'POST', body: JSON.stringify({ message: trimmed }) })
    setTimeout(() => {
      const response = getMockResponse(trimmed)
      setMessages(prev => [...prev, {
        id: Date.now() + 1,
        role: 'assistant',
        text: response,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }])
      setLoading(false)
    }, 600 + Math.random() * 400)
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-6 h-[calc(100vh-8rem)] flex flex-col gap-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">AI Chat</h1>
          <p className="text-xs text-gray-500 mt-0.5">
            Powered by 18 ML models · 3,675 games · 221K shots
            {/* TODO: Phase 15 — Claude API + 10 tools + render_chart */}
          </p>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-gray-500 bg-[#1a1d24] px-2.5 py-1.5 rounded-full border border-gray-800">
          <span className="w-1.5 h-1.5 rounded-full bg-orange-500 animate-pulse" />
          <span>Mock Mode — Phase 15 for live AI</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {messages.map(msg => (
          <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
            {/* Avatar */}
            <div className={`
              shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
              ${msg.role === 'assistant'
                ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                : 'bg-blue-500/20 text-blue-400 border border-blue-500/30'}
            `}>
              {msg.role === 'assistant' ? '🏀' : (user?.email?.[0]?.toUpperCase() || 'U')}
            </div>

            {/* Bubble */}
            <div className={`
              max-w-[85%] rounded-2xl px-4 py-3 space-y-1
              ${msg.role === 'assistant'
                ? 'bg-[#1a1d24] border border-gray-800 rounded-tl-sm'
                : 'bg-blue-600 rounded-tr-sm'}
            `}>
              {msg.role === 'assistant'
                ? renderMarkdown(msg.text)
                : <p className="text-sm text-white">{msg.text}</p>
              }
              <p className="text-[10px] text-gray-600 text-right mt-1">{msg.timestamp}</p>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex gap-3">
            <div className="shrink-0 w-8 h-8 rounded-full bg-orange-500/20 border border-orange-500/30 flex items-center justify-center text-sm">
              🏀
            </div>
            <div className="bg-[#1a1d24] border border-gray-800 rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex gap-1 items-center">
                <span className="w-2 h-2 bg-orange-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-orange-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-orange-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggested queries */}
      <div className="flex gap-2 flex-wrap">
        {SUGGESTED_QUERIES.slice(0, 3).map(q => (
          <button
            key={q}
            onClick={() => sendMessage(q)}
            className="text-xs text-gray-400 bg-[#1a1d24] border border-gray-800 hover:border-orange-500/50 hover:text-orange-400 rounded-full px-3 py-1.5 transition-all truncate max-w-[200px]"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="flex gap-2 bg-[#1a1d24] border border-gray-700 focus-within:border-orange-500/60 rounded-xl p-2 transition-colors">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask about a player, game, or prop..."
          rows={1}
          className="flex-1 bg-transparent text-sm text-white placeholder-gray-600 resize-none focus:outline-none py-1 px-2"
          style={{ minHeight: '36px', maxHeight: '120px' }}
        />
        <button
          onClick={() => sendMessage()}
          disabled={!input.trim() || loading}
          className="shrink-0 bg-orange-500 hover:bg-orange-400 disabled:bg-orange-500/30 disabled:cursor-not-allowed text-white font-semibold px-4 py-1.5 rounded-lg text-sm transition-colors"
        >
          Send
        </button>
      </div>
    </div>
  )
}
