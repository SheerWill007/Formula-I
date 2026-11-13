/**
 * Clerk is optional: BoxUp's race data is public and only predictions need a
 * login. When no publishable key is configured the app still builds and runs,
 * and the predictions page explains that sign-in is not switched on yet.
 */
export const CLERK_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? ''

export const CLERK_ENABLED = CLERK_PUBLISHABLE_KEY.length > 0
