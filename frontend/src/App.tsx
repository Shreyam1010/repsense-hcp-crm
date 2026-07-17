import { useEffect, useState } from 'react'
import { useAppDispatch, useAppSelector } from './store'
import { setBanner } from './store/agentSlice'
import { resetForm } from './store/formDraftSlice'
import { resetChat } from './store/chatSlice'
import { resetAgent } from './store/agentSlice'
import FormPanel from './components/FormPanel'
import ChatPanel from './components/ChatPanel'

export default function App() {
  const dispatch = useAppDispatch()
  const banner = useAppSelector((s) => s.agent.modelBanner)
  const [modelInfo, setModelInfo] = useState<{ active_agent_model?: string; banner?: string | null }>({})

  useEffect(() => {
    fetch('/api/model-info')
      .then((r) => r.json())
      .then((d) => {
        setModelInfo(d)
        if (d.banner) dispatch(setBanner(d.banner))
      })
      .catch(() => {})
  }, [dispatch])

  const resetDemo = async () => {
    await fetch('/api/demo/reset', { method: 'POST' })
    dispatch(resetForm())
    dispatch(resetChat())
    dispatch(resetAgent())
    setTimeout(() => window.location.reload(), 100)
  }

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-lg font-semibold text-slate-800">RepSense</span>
          <span className="text-sm text-slate-400">· Log HCP Interaction</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400 font-mono">
            {modelInfo.active_agent_model ?? 'model…'}
          </span>
          <button
            onClick={resetDemo}
            className="text-xs px-3 py-1.5 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-600"
          >
            Reset demo
          </button>
        </div>
      </header>

      {banner && (
        <div className="bg-amber-50 border-b border-amber-200 text-amber-800 text-sm px-6 py-2 flex items-center gap-2">
          <span>⚠️</span>
          <span>{banner}</span>
        </div>
      )}

      <main className="grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-4 p-4 max-w-[1400px] mx-auto">
        <FormPanel />
        <ChatPanel />
      </main>
    </div>
  )
}
