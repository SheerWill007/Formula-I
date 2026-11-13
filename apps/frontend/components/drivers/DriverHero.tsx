'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import type { DriverProfile } from '@/types/f1'
import { driverImageCandidates, ordinal, teamColour } from '@/lib/driver-image'
import { framingFor } from '@/lib/driver-framing'
import dynamic from 'next/dynamic'
import { withSample } from '@/lib/driver-sample'

const DriverInsights = dynamic(() => import('./DriverInsights'), { loading: () => null })
import { ageFromDob, DRIVER_LIST, flagEmoji, getDriverMeta } from '@/lib/driver-meta'
import './driver.css'

function Figure({ code, alt, headshot, number }: { code: string; alt: string; headshot?: string | null; number?: number }) {
  const candidates = driverImageCandidates(code, headshot)
  const [idx, setIdx] = useState(0)
  const current = candidates[idx]
  const fr = framingFor(code)
  const isCutout = current?.kind === 'cutout'
  return (
    <div
      className="dp-figure"
      data-kind={isCutout ? fr.kind : 'headshot'}
      style={isCutout ? { ['--fig-h' as string]: `${fr.height}%`, ['--fig-x' as string]: `${fr.x}%` } : undefined}
    >
      {number != null && <div className="dp-ghost" aria-hidden>{number}</div>}
      {current && (
        // Plain img: private local files and remote headshots, with onError fallback.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={current.src}
          src={current.src}
          alt={current.kind === 'cutout' ? `${alt} in race gear` : `${alt} portrait`}
          className={current.kind}
          onError={() => setIdx(i => i + 1)}
        />
      )}
    </div>
  )
}

function DriverPicker({ current }: { current: string }) {
  const router = useRouter()
  return (
    <div className="dp-picker">
      <Link href="/drivers" className="dp-back">All drivers</Link>
      <label className="dp-visually-hidden" htmlFor="dp-switch">Switch driver</label>
      <select id="dp-switch" value={current.toUpperCase()} onChange={e => router.push(`/drivers/${e.target.value}`)}>
        {!DRIVER_LIST.some(d => d.code === current.toUpperCase()) && <option value={current.toUpperCase()}>{current.toUpperCase()}</option>}
        {DRIVER_LIST.map(d => <option key={d.code} value={d.code}>{d.name}</option>)}
      </select>
    </div>
  )
}

const SECTIONS = [
  { id: 'heatmap', label: 'Heatmap' },
  { id: 'style', label: 'Driving style' },
  { id: 'trajectory', label: 'Trajectory' },
]

export default function DriverHero({ profile: raw }: { profile: DriverProfile }) {
  const { profile, sampled } = withSample(raw)
  const { identity: id, career, recent_races, style } = profile
  const colour = teamColour(id?.team_colour)
  const meta = getDriverMeta(profile.code)
  const name = id?.full_name ?? meta?.name ?? profile.code
  const career_rows: [string, string][] = career
    ? [
        ['Grand Prix', String(career.grands_prix)],
        ['Wins', String(career.wins)],
        ['Podiums', String(career.podiums)],
        ['Pole positions', String(career.poles)],
        ['Career points', Math.round(career.career_points).toLocaleString('en-GB')],
      ]
    : []

  return (
    <div style={{ ['--dp-team' as string]: colour }}>
      <div className="dp">
        <div className="dp-floor" />
        <div className="dp-stage">
          <section className="dp-col" aria-label="Driver profile">
            <DriverPicker current={profile.code} />
            <div className="dp-head">
              <div>
                <p className="dp-kicker">Driver profile</p>
                <h1>{name}</h1>
                <p className="dp-teamline">
                  {meta && <span aria-hidden>{flagEmoji(meta.country)}</span>}
                  <i className="dp-dot" />
                  {id?.team_name ?? 'Team unknown'}
                </p>
              </div>
              {id && <span className="dp-num" aria-label={`Number ${id.driver_number}`}>{id.driver_number}</span>}
            </div>
            {meta && (
              <div className="dp-card">
                <div className="dp-row"><span>Nationality</span><span>{meta.nationality}</span></div>
                <div className="dp-row"><span>Age</span><span>{ageFromDob(meta.dob)} years</span></div>
                <div className="dp-row"><span>Height</span><span>{meta.heightCm ? `${meta.heightCm} cm` : '-'}</span></div>
                <div className="dp-row"><span>Weight</span><span>{meta.weightKg ? `${meta.weightKg} kg` : '-'}</span></div>
              </div>
            )}
            {(style?.archetype || career) && (
              <div className="dp-card">
                {style?.archetype && (
                  <div className="dp-row"><span>Style</span><span className="dp-chip">{style.archetype}</span></div>
                )}
                {career && (
                  <>
                    <div className="dp-row"><span>Seasons</span><span>{career.seasons}</span></div>
                    <div className="dp-row"><span>Debut</span><span>{career.first_season ?? '-'}</span></div>
                  </>
                )}
              </div>
            )}
          </section>

          <Figure code={profile.code} alt={`${name}${id?.team_name ? `, ${id.team_name}` : ''}`} number={id?.driver_number} />

          <section className="dp-col" aria-label="Career statistics">
            <h2 className="dp-side-h">Career statistics</h2>
            {career_rows.length > 0 && (
              <div className="dp-card dp-big">
                {career_rows.map(([k, v]) => (
                  <div className="dp-row" key={k}><span>{k}</span><span>{v}</span></div>
                ))}
              </div>
            )}
            {recent_races.length > 0 && (
              <div className="dp-card">
                <p className="dp-h">Last races</p>
                {recent_races.map(r => (
                  <div className="dp-race" key={`${r.year}-${r.round}`}>
                    <span>{r.year} {r.race_name ?? `Round ${r.round}`}</span>
                    <span className={`dp-pos${r.position === 1 ? ' win' : ''}`}>
                      {r.position ? ordinal(r.position) : (r.position_text ?? 'DNF')}
                    </span>
                    <small>Grid {r.grid || 'PL'} · {r.constructor_name ?? ''}</small>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
        {(sampled.career || sampled.races) && <span className="dp-sample">Sample data</span>}
        <a href="#heatmap" className="dp-scroll-cue">Scroll for more <span aria-hidden>&#8964;</span></a>
      </div>

      <nav className="dp-jump" aria-label="Profile sections">
        {SECTIONS.map(s => <a key={s.id} href={`#${s.id}`}>{s.label}</a>)}
      </nav>
      <div className="dp-below"><DriverInsights profile={profile} sampled={sampled} /></div>
    </div>
  )
}
