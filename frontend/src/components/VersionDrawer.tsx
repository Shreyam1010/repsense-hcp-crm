import { useEffect, useState } from 'react'

interface Version {
  version: number
  snapshot: Record<string, unknown>
  diff: { field: string; from: unknown; to: unknown }[]
  reason_for_change?: string
  actor_id: string
  created_at: string
}

export default function VersionDrawer({ interactionId, onClose }: { interactionId: string; onClose: () => void }) {
  const [versions, setVersions] = useState<Version[]>([])

  useEffect(() => {
    fetch(`/api/interactions/${interactionId}/versions`).then((r) => r.json()).then(setVersions).catch(() => {})
  }, [interactionId])

  return (
    <div className="fixed inset-0 bg-black/30 flex justify-end z-50" onClick={onClose}>
      <div className="bg-white w-[420px] h-full overflow-y-auto p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-slate-800">Version history</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">✕</button>
        </div>
        <p className="text-xs text-slate-500 mb-4">
          Append-only. v1 is retained verbatim; the database refuses any UPDATE or DELETE
          on a filed version (21 CFR Part 11 audit trail).
        </p>
        <div className="space-y-3">
          {versions.map((v) => {
            const sentiment = (v.snapshot.sentiment as Record<string, unknown>) || {}
            return (
              <div key={v.version} className="border border-slate-200 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm text-slate-800">v{v.version}</span>
                  <span className="text-xs text-slate-400">{new Date(v.created_at).toLocaleString()}</span>
                </div>
                <div className="text-xs text-slate-600">
                  sentiment: <b>{String(sentiment.label ?? '—')}</b>
                  {sentiment.barrier_code ? ` · barrier: ${String(sentiment.barrier_code)}` : ''}
                  {sentiment.rationale_quote ? <div className="italic text-slate-400 mt-0.5">“{String(sentiment.rationale_quote)}”</div> : null}
                </div>
                <div className="text-xs text-slate-400 mt-1">by {v.actor_id}</div>
                {v.reason_for_change && (
                  <div className="text-xs text-amber-700 mt-1 bg-amber-50 rounded px-2 py-1">
                    reason: {v.reason_for_change}
                  </div>
                )}
                {v.diff?.length > 0 && (
                  <div className="text-xs text-slate-500 mt-1">
                    {v.diff.map((d, i) => (
                      <div key={i}>{d.field}: <span className="line-through text-slate-400">{JSON.stringify(d.from)}</span> → <b>{JSON.stringify(d.to)}</b></div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
