import type { Metadata } from 'next'
import PostCard from '@/components/blog/PostCard'
import { getAllPosts } from '@/lib/blog'
import '@/components/blog/blog.css'

export const metadata: Metadata = {
  title: 'Blog | BoxUp',
  description: 'Build notes, race breakdowns and model write-ups from BoxUp.',
}

export default function BlogIndex() {
  const posts = getAllPosts()
  return (
    <div className="layout-wrapper">
      <p className="bx-kicker">Blog</p>
      <h1 className="bx-page-title">Notes from the pit wall</h1>
      <p className="bx-page-sub">Build notes, race breakdowns and how the BoxUp models work.</p>
      {posts.length > 0 ? (
        <div className="bx-post-grid">
          {posts.map(p => <PostCard key={p.slug} post={p} />)}
        </div>
      ) : (
        <div className="bx-empty">The first posts are on the way.</div>
      )}
    </div>
  )
}
