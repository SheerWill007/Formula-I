import Link from 'next/link'
import { ArrowRight } from 'lucide-react'
import { formatDate, type PostMeta } from '@/lib/blog'

export function PostMetaLine({ post }: { post: PostMeta }) {
  return (
    <div className="bx-meta">
      <span className="bx-tag">{post.tag}</span>
      <time dateTime={post.date}>{formatDate(post.date)}</time>
      <span>{post.readingMinutes} min read</span>
    </div>
  )
}

export default function PostCard({ post }: { post: PostMeta }) {
  return (
    <Link href={`/blog/${post.slug}`} className="bx-post-card">
      <PostMetaLine post={post} />
      <h3>{post.title}</h3>
      <p>{post.summary}</p>
      <span className="bx-read">Read post <ArrowRight size={15} strokeWidth={2.4} aria-hidden="true" /></span>
    </Link>
  )
}
