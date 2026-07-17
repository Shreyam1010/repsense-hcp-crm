import { useEffect, useMemo, useState } from 'react'
import { useAppDispatch, useAppSelector } from '../store'
import { userEditedField, acceptSuggestion, keepMine } from '../store/formDraftSlice'
import VersionDrawer from './VersionDrawer'
import { Field } from './Field'

interface Hcp { hcp_id: string; full_name: string; specialty: string; institution: string }
interface Product { product_id: string; brand_name: string }

const SENTIMENTS = ['positive', 'neutral', 'negative'] as const

export default function FormPanel() {
  const dispatch = useAppDispatch()
  const { values, fieldMeta, pendingSuggestions, complianceFlags, interactionId, status, locked, version } =
    useAppSelector((s) => s.formDraft)
  const filtered = useAppSelector((s) => s.agent.filteredMaterials)
  const suggestions = useAppSelector((s) => s.agent.suggestions)
  const [hcps, setHcps] = useState<Hcp[]>([])
  const [, setProducts] = useState<Product[]>([])
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    fetch('/api/hcps').then((r) => r.json()).then(setHcps).catch(() => {})
    fetch('/api/products').then((r) => r.json()).then(setProducts).catch(() => {})
  }, [])

  const hcpName = useMemo(() => {
    const id = values['hcp_id'] as string | undefined
    return id ? hcps.find((h) => h.hcp_id === id)?.full_name ?? id : ''
  }, [values, hcps])

  const set = (path: string, value: unknown) => dispatch(userEditedField({ path, value }))
  const sentiment = (values['sentiment'] as Record<string, unknown>) || {}
  const sentimentInferred = sentiment.source === 'model_inferred' && !sentiment.confirmed_by_rep

  const submitForm = async () => {
    const res = await fetch('/api/interactions/submit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ form: values, hcp_id: values['hcp_id'], interaction_id: interactionId }),
    })
    if (res.ok) window.location.reload()
  }

  return (
    <section className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-slate-800">Interaction Details</h2>
        <div className="flex items-center gap-2">
          {status !== 'DRAFT' && (
            <span className={`text-xs px-2 py-1 rounded-md font-medium ${
              status === 'AMENDED' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
              {status}{interactionId ? ` · v${version}` : ''}{locked ? ' · LOCKED' : ''}
            </span>
          )}
          {interactionId && (
            <button onClick={() => setDrawerOpen(true)}
              className="text-xs px-2 py-1 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-600">
              Version history
            </button>
          )}
        </div>
      </div>

      {complianceFlags.length > 0 && (
        <div className="mb-4 space-y-1">
          {complianceFlags.map((f, i) => (
            <div key={i} className={`text-xs px-3 py-2 rounded-md ${
              f.severity === 'block' ? 'bg-red-50 text-red-700 border border-red-200'
                : f.severity === 'warn' ? 'bg-amber-50 text-amber-700 border border-amber-200'
                : 'bg-slate-50 text-slate-600'}`}>
              <span className="font-medium">{f.code}</span> — {f.message}
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <Field label="HCP Name" meta={fieldMeta['hcp_id']}>
          <input list="hcp-list" value={hcpName} disabled={locked}
            onChange={(e) => {
              const h = hcps.find((x) => x.full_name === e.target.value)
              set('hcp_id', h ? h.hcp_id : e.target.value)
            }}
            placeholder="Search or select HCP…" className={inputCls} />
          <datalist id="hcp-list">
            {hcps.map((h) => <option key={h.hcp_id} value={h.full_name}>{h.specialty} · {h.institution}</option>)}
          </datalist>
        </Field>

        <Field label="Interaction Type" meta={fieldMeta['interaction_type']}>
          <select value={(values['interaction_type'] as string) || ''} disabled={locked}
            onChange={(e) => set('interaction_type', e.target.value)} className={inputCls}>
            <option value="">Select…</option>
            {['face_to_face', 'remote_video', 'phone', 'conference', 'group_event'].map((t) =>
              <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
          </select>
        </Field>

        <Field label="Date" meta={fieldMeta['date']}>
          <input value={dateOf(values)} disabled={locked}
            onChange={(e) => set('interaction_datetime_claimed', e.target.value)} className={inputCls} />
        </Field>
        <Field label="Time" meta={fieldMeta['time']}>
          <input value={timeOf(values)} disabled className={inputCls} />
        </Field>
      </div>

      <Field label="Topics Discussed" meta={fieldMeta['topics_discussed'] || fieldMeta['summary_text']}>
        <textarea value={topicsText(values)} disabled={locked}
          onChange={(e) => set('summary_text', e.target.value)}
          placeholder="Enter key discussion points…" rows={2} className={inputCls} />
      </Field>

      <Field label="Materials Shared" meta={fieldMeta['materials_shared']}>
        <div className="text-sm text-slate-600">
          {(values['materials_shared'] as string[] | undefined)?.length
            ? (values['materials_shared'] as string[]).join(', ')
            : <span className="text-slate-400">No materials added.</span>}
        </div>
        {filtered.length > 0 && (
          <div className="mt-1 text-xs text-slate-500">
            {filtered.length} asset{filtered.length > 1 ? 's' : ''} excluded:{' '}
            {filtered.map((m) => `${m.title} (${m.reason.toLowerCase()})`).join(' · ')}
          </div>
        )}
      </Field>

      <div className="mt-4">
        <label className="block text-xs font-medium text-slate-500 mb-1.5">
          Observed/Inferred HCP Sentiment
          {sentimentInferred && (
            <span className="ml-2 inline-flex items-center gap-1 text-amber-600" title={String(sentiment.rationale_quote || '')}>
              ⚠ AI-inferred · confirm
            </span>
          )}
          {Boolean(sentiment.confirmed_by_rep) && <span className="ml-2 text-emerald-600">✓ confirmed</span>}
        </label>
        <div className={`flex gap-4 rounded-md p-1 ${flashClass(fieldMeta['sentiment'])}`}>
          {SENTIMENTS.map((s) => (
            <label key={s} className="flex items-center gap-1.5 text-sm text-slate-700 capitalize cursor-pointer">
              <input type="radio" name="sentiment" checked={sentiment.label === s} disabled={locked}
                onChange={() => set('sentiment', { ...sentiment, label: s, source: 'rep_stated', confirmed_by_rep: true })} />
              {s}
            </label>
          ))}
          {sentiment.barrier_code ? (
            <span className="ml-auto text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded self-center">
              Barrier: {String(sentiment.barrier_code).replace(/_/g, ' ')}
            </span>
          ) : null}
        </div>
        {sentimentInferred && !locked && (
          <button onClick={() => set('sentiment', { ...sentiment, confirmed_by_rep: true })}
            className="mt-2 text-xs px-3 py-1.5 rounded-md bg-emerald-600 text-white hover:bg-emerald-700">
            Confirm “{String(sentiment.label)}”
          </button>
        )}
      </div>

      <Field label="Outcomes" meta={fieldMeta['outcomes']}>
        <textarea value={(values['outcomes'] as string) || ''} disabled={locked}
          onChange={(e) => set('outcomes', e.target.value)} rows={2}
          placeholder="Key outcomes or agreements…" className={inputCls} />
      </Field>

      {Object.keys(pendingSuggestions).length > 0 && (
        <div className="mt-4 space-y-2">
          {Object.entries(pendingSuggestions).map(([path, s]) => (
            <div key={path} className="flex items-center gap-2 text-xs bg-indigo-50 border border-indigo-200 rounded-md px-3 py-2">
              <span className="text-indigo-700">AI suggested <b>{path}</b> = {JSON.stringify(s.value)}</span>
              <button onClick={() => dispatch(acceptSuggestion(path))} className="ml-auto px-2 py-0.5 rounded bg-indigo-600 text-white">Accept</button>
              <button onClick={() => dispatch(keepMine(path))} className="px-2 py-0.5 rounded bg-white border border-slate-300">Keep mine</button>
            </div>
          ))}
        </div>
      )}

      {suggestions.length > 0 && (
        <div className="mt-4">
          <label className="block text-xs font-medium text-slate-500 mb-1.5">AI Suggested Follow-ups</label>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((s, i) => (
              <span key={i} title={s.rationale_quote || ''}
                className="text-xs px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                + {s.label}
              </span>
            ))}
          </div>
        </div>
      )}

      {!locked && values['hcp_id'] ? (
        <button onClick={submitForm}
          className="mt-5 w-full py-2 rounded-md bg-slate-800 text-white text-sm font-medium hover:bg-slate-900">
          Submit call report
        </button>
      ) : null}

      {drawerOpen && interactionId && (
        <VersionDrawer interactionId={interactionId} onClose={() => setDrawerOpen(false)} />
      )}
    </section>
  )
}

const inputCls = 'w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 disabled:bg-slate-50 disabled:text-slate-500'

function flashClass(meta?: { updatedAt: number; source: string; kind?: string }) {
  if (!meta || meta.source !== 'agent') return ''
  if (Date.now() - meta.updatedAt > 1200) return ''
  return meta.kind === 'edit' ? 'flash-edit' : 'flash-fill'
}

function dateOf(values: Record<string, unknown>): string {
  const dt = values['interaction_datetime_claimed'] as string | undefined
  if (dt) return dt.slice(0, 10)
  return new Date().toISOString().slice(0, 10)
}
function timeOf(values: Record<string, unknown>): string {
  const dt = values['interaction_datetime_claimed'] as string | undefined
  if (dt && dt.includes('T')) return dt.slice(11, 16)
  return new Date().toTimeString().slice(0, 5)
}
function topicsText(values: Record<string, unknown>): string {
  const s = values['summary_text'] as string | undefined
  if (s) return s
  const topics = values['topics_discussed'] as { key_message?: string }[] | undefined
  return topics?.map((t) => t.key_message).filter(Boolean).join('; ') ?? ''
}
