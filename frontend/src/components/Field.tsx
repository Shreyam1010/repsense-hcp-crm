import type { ReactNode } from 'react'
import type { FieldMeta } from '../store/formDraftSlice'

export function Field({ label, meta, children }: { label: string; meta?: FieldMeta; children: ReactNode }) {
  const flash = meta && meta.source === 'agent' && Date.now() - meta.updatedAt < 1200
    ? (meta.kind === 'edit' ? 'flash-edit' : 'flash-fill')
    : ''
  return (
    <div className="mt-4">
      <label className="block text-xs font-medium text-slate-500 mb-1.5">{label}</label>
      <div key={meta?.updatedAt ?? 0} className={`rounded-md ${flash}`}>{children}</div>
    </div>
  )
}
