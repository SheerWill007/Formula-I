'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { NAV_ITEMS, isActive } from '@/lib/nav'

const BOTTOM_ITEMS = NAV_ITEMS.filter(item => item.bottom)

/** Always-visible tab bar on phones; hidden on larger screens via nav.css. */
export default function BottomNav() {
  const pathname = usePathname()

  return (
    <nav className="bottom-nav-shell" aria-label="Quick navigation">
      <div className="bottom-nav-inner">
        {BOTTOM_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href)
          return (
            <Link
              key={href}
              href={href}
              className={`bottom-nav-link ${active ? 'active' : ''}`}
              aria-current={active ? 'page' : undefined}
            >
              <Icon size={18} strokeWidth={active ? 2.5 : 1.9} />
              <span className="bottom-nav-label">{label}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
