import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { useIsGuest } from '../hooks/sharedCrew/useSharedCrew'
import { isOwnerOnlyPath } from '../lib/ownerOnly'
import OwnerOnlyState from './OwnerOnlyState'

/** Shows the Owner-only state instead of a page a Shared Crew guest cannot use. */
export default function OwnerOnlyGate({ children }: { children: ReactNode }) {
  const isGuest = useIsGuest()
  const { pathname } = useLocation()
  if (isGuest && isOwnerOnlyPath(pathname)) return <OwnerOnlyState />
  return <>{children}</>
}
