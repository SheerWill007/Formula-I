import React from 'react'

// The root layout already renders <main>; this only constrains the width.
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="dashboard-shell" style={{ padding: '32px 24px', maxWidth: 1248, margin: '0 auto' }}>
      {children}
    </div>
  )
}
