import type { Metadata } from 'next'
import Link from 'next/link'
import { DRIVER_LIST, flagEmoji } from '@/lib/driver-meta'
import '@/components/drivers/driver.css'

export const metadata: Metadata = { title: 'Drivers | BoxUp' }

export default function DriversIndex() {
  return (
    <div className="layout-wrapper">
      <div className="dp-index">
        <p className="dp-kicker">2026 grid</p>
        <h1>Drivers</h1>
        <p className="dp-sub">Pick a driver to see their profile, season heatmap and driving style.</p>
        <ul className="dp-index-grid">
          {DRIVER_LIST.map(d => (
            <li key={d.code}>
              <Link href={`/drivers/${d.code}`} className="dp-index-card">
                <span aria-hidden className="dp-index-flag">{flagEmoji(d.country)}</span>
                <span className="dp-index-name">{d.name}</span>
                <span className="dp-index-code">{d.code}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
