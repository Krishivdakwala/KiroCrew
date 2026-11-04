// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OwnerOnlyGate from './OwnerOnlyGate'
import ErrorBoundary from './ErrorBoundary'
import { ApiError } from '../api/apiError'

const guest = vi.hoisted(() => ({ value: true }))
vi.mock('../hooks/sharedCrew/useSharedCrew', () => ({ useIsGuest: () => guest.value }))

function at(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <OwnerOnlyGate><div data-testid="page">page</div></OwnerOnlyGate>
    </MemoryRouter>,
  )
}

afterEach(() => { cleanup(); guest.value = true })

describe('OwnerOnlyGate', () => {
  it('shows the Owner-only state to a guest on an owner-only page', () => {
    at('/settings/people')
    expect(screen.getByTestId('owner-only')).toBeTruthy()
    expect(screen.queryByTestId('page')).toBeNull()
  })

  it('leaves a guest on an in-crew page alone', () => {
    at('/chat/abc')
    expect(screen.getByTestId('page')).toBeTruthy()
    expect(screen.queryByTestId('owner-only')).toBeNull()
  })

  it('never blocks the owner', () => {
    guest.value = false
    at('/settings')
    expect(screen.getByTestId('page')).toBeTruthy()
  })

  it('renders the same state when a page throws a 403 owner_only', () => {
    const Throws = () => { throw new ApiError(403, 'forbidden', JSON.stringify({ code: 'owner_only' })) }
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<ErrorBoundary><Throws /></ErrorBoundary>)
    expect(screen.getByTestId('owner-only')).toBeTruthy()
  })
})
