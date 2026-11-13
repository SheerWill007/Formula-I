import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowLeft } from 'lucide-react'
import BlogChart from '@/components/blog/AlonsoCharts'
import { PostMetaLine } from '@/components/blog/PostCard'
import { getAllPosts, getHeadings, getPost, slugify } from '@/lib/blog'
import '@/components/blog/blog.css'

type Params = { params: Promise<{ slug: string }> }

export function generateStaticParams() {
  return getAllPosts().map(p => ({ slug: p.slug }))
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const post = getPost((await params).slug)
  if (!post) return { title: 'Post not found | BoxUp' }
  return {
    title: `${post.title} | BoxUp`,
    description: post.summary,
    openGraph: { title: post.title, description: post.summary, type: 'article', publishedTime: post.date },
  }
}

export default async function PostPage({ params }: Params) {
  const post = getPost((await params).slug)
  if (!post) notFound()
  const headings = getHeadings(post.body)

  return (
    <div className="layout-wrapper">
      <article className="bx-article">
        <Link href="/blog" className="bx-back">
          <ArrowLeft size={15} strokeWidth={2.4} aria-hidden="true" /> All posts
        </Link>
        {post.kicker && <p className="bx-kicker">{post.kicker}</p>}
        <h1>
          {post.emphasis && post.title.endsWith(post.emphasis) ? (
            <>
              {post.title.slice(0, -post.emphasis.length)}
              <em>{post.emphasis}</em>
            </>
          ) : (
            post.title
          )}
        </h1>
        {post.summary && <p className="bx-deck">{post.summary}</p>}
        <PostMetaLine post={post} />
        {headings.length > 3 && (
          <nav className="bx-toc" aria-label="In this article">
            <p>In this article</p>
            <ol>
              {headings.map(h => (
                <li key={h.id}><a href={`#${h.id}`}>{h.text}</a></li>
              ))}
            </ol>
          </nav>
        )}
        <div className="bx-prose">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              table: ({ children }) => <div className="table-wrap"><table>{children}</table></div>,
              h2: ({ children }) => <h2 id={slugify(textOf(children))}>{children}</h2>,
              // A ```chart fence holds a chart id, e.g. team-pace. See components/blog/AlonsoCharts.
              pre: ({ children }) => {
                const child = Array.isArray(children) ? children[0] : children
                const cls = (child as { props?: { className?: string } } | undefined)?.props?.className
                return cls?.includes('language-chart') ? <>{children}</> : <pre>{children}</pre>
              },
              code: ({ className, children }) =>
                className?.includes('language-chart')
                  ? <BlogChart id={textOf(children).trim()} />
                  : <code className={className}>{children}</code>,
            }}
          >
            {post.body}
          </ReactMarkdown>
        </div>
      </article>
    </div>
  )
}

/** Plain text of a heading's children, so its id matches the contents box. */
function textOf(node: React.ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (node && typeof node === 'object' && 'props' in node) return textOf((node as { props: { children?: React.ReactNode } }).props.children)
  return ''
}
