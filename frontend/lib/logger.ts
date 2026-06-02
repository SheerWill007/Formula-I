/**
 * Centralized logging service for the application
 * Replaces console.log/error/warn with structured logging
 * Can be easily extended to send logs to external services (Sentry, LogRocket, etc.)
 */

type LogLevel = 'info' | 'warn' | 'error' | 'debug'

interface LogContext {
  [key: string]: unknown
}

class Logger {
  private isDevelopment = process.env.NODE_ENV === 'development'
  private isProduction = process.env.NODE_ENV === 'production'

  /**
   * Log an informational message
   */
  info(message: string, context?: LogContext): void {
    this.log('info', message, context)
  }

  /**
   * Log a warning message
   */
  warn(message: string, context?: LogContext): void {
    this.log('warn', message, context)
  }

  /**
   * Log an error message
   */
  error(message: string, error?: Error | unknown, context?: LogContext): void {
    const errorContext = {
      ...context,
      error: error instanceof Error ? {
        message: error.message,
        stack: error.stack,
        name: error.name,
      } : error,
    }
    this.log('error', message, errorContext)
  }

  /**
   * Log a debug message (only in development)
   */
  debug(message: string, context?: LogContext): void {
    if (this.isDevelopment) {
      this.log('debug', message, context)
    }
  }

  /**
   * Internal logging method
   */
  private log(level: LogLevel, message: string, context?: LogContext): void {
    const timestamp = new Date().toISOString()
    const logData = {
      timestamp,
      level,
      message,
      ...context,
    }

    // In development, use console for better DX
    if (this.isDevelopment) {
      const consoleMethod = level === 'error' ? console.error : 
                           level === 'warn' ? console.warn : 
                           console.log

      consoleMethod(`[${level.toUpperCase()}] ${message}`, context || '')
      return
    }

    // In production, you can send to external logging service
    if (this.isProduction) {
      // TODO: Send to external logging service (Sentry, LogRocket, etc.)
      // Example: Sentry.captureMessage(message, { level, extra: context })
      
      // For now, still log to console in production but with structured format
      console.log(JSON.stringify(logData))
    }
  }

  /**
   * Log API errors with additional context
   */
  apiError(endpoint: string, error: Error | unknown, context?: LogContext): void {
    this.error(`API Error: ${endpoint}`, error, {
      endpoint,
      ...context,
    })
  }

  /**
   * Log fetch failures
   */
  fetchError(resource: string, error: Error | unknown, context?: LogContext): void {
    this.error(`Fetch failed: ${resource}`, error, {
      resource,
      ...context,
    })
  }
}

// Export singleton instance
export const logger = new Logger()

// Export type for use in other files
export type { LogLevel, LogContext }
