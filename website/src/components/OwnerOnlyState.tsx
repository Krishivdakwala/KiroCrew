import { Lock } from 'lucide-react'
import { i18nT } from '../i18n/t'

/** The one state a guest sees on a page only the owner can use. */
export default function OwnerOnlyState() {
  return (
    <div role="status" data-testid="owner-only" className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center text-muted">
      <Lock size={20} aria-hidden />
      <div className="text-sm font-medium text-text-strong">{i18nT('components.errorBoundary.owner_only')}</div>
    </div>
  )
}
