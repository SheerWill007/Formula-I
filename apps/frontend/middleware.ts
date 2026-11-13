import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextResponse } from 'next/server'

// Only the prediction lab is members-only; everything else stays public.
const isProtectedRoute = createRouteMatcher(['/predictions(.*)'])

const clerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY)

export default clerkEnabled
  ? clerkMiddleware(async (auth, request) => {
      if (isProtectedRoute(request)) await auth.protect()
    })
  : () => NextResponse.next()

export const config = {
  matcher: ['/((?!_next|[^?]*\\.[^?]*$).*)', '/(api|trpc)(.*)'],
}
