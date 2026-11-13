import type { Metadata } from 'next'
import LegalPage from '@/components/blog/LegalPage'

export const metadata: Metadata = {
  title: 'Privacy | BoxUp',
  description: 'What BoxUp stores, who processes it, and how to ask for it to be removed.',
}

const ISSUES_URL = 'https://github.com/SheerWill007/Formula-I/issues'

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy" updated="14 November 2026">
      <p>
        BoxUp is an open source Formula 1 analytics project. This page describes, in plain language,
        what the service stores and which providers process data on its behalf.
      </p>

      <h2>Browsing without an account</h2>
      <p>
        Sessions, telemetry, strategy, schedule, standings, driver profiles and the blog are open to everyone
        and need no account. Race data shown in the app comes from public motorsport sources and is not personal data.
      </p>

      <h2>Your account</h2>
      <p>
        Race predictions need you to sign in. Sign in and sign up are handled by Clerk. Clerk stores your
        sign in details, such as your email address, and issues the session token the app uses to recognise
        you. BoxUp never sees your password.
      </p>

      <h2>Who else processes data</h2>
      <ul>
        <li><strong>Clerk</strong> for authentication.</li>
        <li><strong>Vercel</strong> hosts the website; <strong>Vercel Analytics and Speed Insights</strong> record aggregate page views and performance.</li>
        <li><strong>Render</strong> hosts the API and <strong>Neon</strong> hosts the database.</li>
      </ul>

      <h2>Cookies</h2>
      <p>
        Clerk sets the cookies needed to keep you signed in. BoxUp also remembers your theme and sound
        choice in your browser. BoxUp does not use advertising cookies.
      </p>

      <h2>Deleting your data</h2>
      <p>
        You can delete your account from your Clerk profile. For anything else, open an issue on{' '}
        <a href={ISSUES_URL}>GitHub</a>.
      </p>
    </LegalPage>
  )
}
