'use client'

import { use, useEffect, useState } from 'react'
import DriverHero from '@/components/drivers/DriverHero'
import { api, APIError } from '@/lib/api'
import { normaliseDriverCode } from '@/lib/driver-image'
import type { DriverProfile } from '@/types/f1'
import '@/components/drivers/driver.css'

type State = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ok'; profile: DriverProfile }

export default function DriverPage({ params }: { params: Promise<{ code: string }> }) {
  const { code: raw } = use(params)
  const code = normaliseDriverCode(raw)
  const [state, setState] = useState<State>(
    code ? { status: 'loading' } : { status: 'error', message: 'That is not a valid driver code.' },
  )

  useEffect(() => {
    if (!code) return
    let cancelled = false
    api.drivers.profile(code)
      .then(profile => !cancelled && setState({ status: 'ok', profile }))
      .catch(e => {
        if (cancelled) return
        setState({
          status: 'error',
          message: e instanceof APIError && e.status === 404
            ? `No data for ${code.toUpperCase()} yet.`
            : 'Could not load this driver. Try again shortly.',
        })
      })
    return () => { cancelled = true }
  }, [code])

  return (
    <div className="layout-wrapper" style={{ maxWidth: 1440 }}>
      {state.status === 'ok' ? (
        <DriverHero profile={state.profile} />
      ) : (
        <p className="dp-state" role="status">
          {state.status === 'loading' ? 'Loading driver...' : state.message}
        </p>
      )}
    </div>
  )
}
