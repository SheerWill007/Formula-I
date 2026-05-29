import React from 'react'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div style={{ minHeight: '100vh', background: '#FAFAFA' }}>
      <main style={{
        padding: '32px 40px',
        minHeight: '100vh',
        background: '#FAFAFA',
      }}>
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
          {children}
        </div>
      </main>
    </div>
  )
}
