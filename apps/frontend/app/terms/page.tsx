import type { Metadata } from 'next'
import LegalPage from '@/components/blog/LegalPage'

export const metadata: Metadata = {
  title: 'Terms | BoxUp',
  description: 'The ground rules for using BoxUp.',
}

const ISSUES_URL = 'https://github.com/SheerWill007/Formula-I/issues'

export default function TermsPage() {
  return (
    <LegalPage title="Terms" updated="14 November 2026">
      <p>By using BoxUp you agree to the points below.</p>

      <h2>An independent project</h2>
      <p>
        BoxUp is not affiliated with, or endorsed by, Formula 1, any team, driver or governing body.
        Formula 1 and related marks belong to their owners.
      </p>

      <h2>Data and predictions</h2>
      <p>
        Data is gathered from public sources and may be incomplete, delayed or wrong. Predictions are
        statistical estimates from a model and are not guarantees. Do not rely on them for betting or any
        decision where an error would cause harm. The service is provided as is, without warranty.
      </p>

      <h2>Your account</h2>
      <p>
        You are responsible for activity on your account. Do not try to disrupt the service, bypass usage
        limits, or access data that is not yours.
      </p>

      <h2>The software</h2>
      <p>
        The BoxUp source code is open source under the GNU AGPL v3, and includes code from the Slipstream
        project under the Apache License 2.0. These terms cover use of the hosted service, not your rights
        to the code, which the licences describe.
      </p>

      <h2>Changes</h2>
      <p>These terms may change. Continued use after a change means you accept the new version.</p>

      <h2>Contact</h2>
      <p>Questions about these terms: open an issue on <a href={ISSUES_URL}>GitHub</a>.</p>
    </LegalPage>
  )
}
