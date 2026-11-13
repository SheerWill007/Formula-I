import { redirect } from 'next/navigation'

// Past race weekends live on the sessions page.
export default function ArchivePage() {
  redirect('/sessions')
}
