import './blog.css'

export default function LegalPage({
  title,
  updated,
  children,
}: {
  title: string
  updated: string
  children: React.ReactNode
}) {
  return (
    <div className="layout-wrapper">
      <article className="bx-article">
        <p className="bx-kicker">Legal</p>
        <h1>{title}</h1>
        <p className="bx-meta">Last updated {updated}</p>
        <div className="bx-prose" style={{ marginTop: 24 }}>{children}</div>
      </article>
    </div>
  )
}
