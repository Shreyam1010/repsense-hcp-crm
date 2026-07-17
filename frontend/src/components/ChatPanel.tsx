import { useEffect, useRef, useState } from 'react'
import { useAppDispatch, useAppSelector } from '../store'
import { addUserMessage, clearClarify } from '../store/chatSlice'
import { clearError } from '../store/agentSlice'
import { streamChat } from '../api/stream'

const PLACEHOLDER =
  'Log interaction details here (e.g., "Met Dr. Sharma, discussed OncoBoost OASIS efficacy, went well, left the Phase III reprint") or ask for help.'

export default function ChatPanel() {
  const dispatch = useAppDispatch()
  const { messages, streamingText, streaming, clarify, conversationId } = useAppSelector((s) => s.chat)
  const { toolLog, error } = useAppSelector((s) => s.agent)
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, streamingText, toolLog])

  const send = async (text: string) => {
    const msg = text.trim()
    if (!msg || streaming) return
    setInput('')
    dispatch(addUserMessage(msg))
    dispatch(clearError())
    await streamChat(dispatch, msg, conversationId)
  }

  const recentTools = toolLog.slice(-4)

  return (
    <section className="bg-white rounded-xl border border-slate-200 flex flex-col h-[calc(100vh-8rem)]">
      <div className="px-4 py-3 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <span className="text-base">🤖</span>
          <div>
            <div className="text-sm font-semibold text-slate-800">AI Assistant</div>
            <div className="text-xs text-slate-400">Log interaction via chat</div>
          </div>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && !streaming && (
          <div className="text-sm text-slate-400 bg-slate-50 rounded-lg p-3">{PLACEHOLDER}</div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
            <div className={`max-w-[85%] text-sm px-3 py-2 rounded-lg whitespace-pre-wrap ${
              m.role === 'user' ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-800'}`}>
              {m.content}
            </div>
          </div>
        ))}
        {streaming && streamingText && (
          <div className="flex justify-start">
            <div className="max-w-[85%] text-sm px-3 py-2 rounded-lg bg-slate-100 text-slate-800 whitespace-pre-wrap">
              {streamingText}
            </div>
          </div>
        )}

        {recentTools.length > 0 && streaming && (
          <div className="flex flex-wrap gap-1.5">
            {recentTools.map((t, i) => (
              <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-white font-mono">
                🔧 {t.name}
              </span>
            ))}
          </div>
        )}

        {clarify && (
          <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3">
            <div className="text-xs text-indigo-700 mb-2">{clarify.question}</div>
            <div className="flex flex-col gap-1.5">
              {clarify.options.map((o) => (
                <button key={o.value} onClick={() => { dispatch(clearClarify()); send(`It's ${o.label.split(' · ')[0]} (${o.value})`) }}
                  className="text-left text-xs px-3 py-2 rounded-md bg-white border border-slate-200 hover:border-indigo-400">
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {error && (
          <div className="text-xs bg-red-50 border border-red-200 text-red-700 rounded-md px-3 py-2">
            {error.code === 'no_agent'
              ? 'The assistant is offline — set GROQ_API_KEY in .env and restart the backend.'
              : error.message}
            {error.retry_after ? ` (retry in ${error.retry_after}s)` : ''}
          </div>
        )}
      </div>

      <form className="p-3 border-t border-slate-100 flex gap-2"
        onSubmit={(e) => { e.preventDefault(); send(input) }}>
        <input value={input} onChange={(e) => setInput(e.target.value)}
          placeholder="Describe interaction…" disabled={streaming}
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400" />
        <button type="submit" disabled={streaming || !input.trim()}
          className="px-4 py-2 rounded-md bg-indigo-600 text-white text-sm font-medium disabled:opacity-50">
          {streaming ? '…' : 'Log'}
        </button>
      </form>
    </section>
  )
}
