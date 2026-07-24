import { Component, type ReactNode, type ErrorInfo } from 'react'
import { ErrorFallback } from './ErrorFallback'
import { errorLogger } from '../lib/errorLogger'

interface Props {
  children: ReactNode
  level: 'app' | 'route' | 'section'
  /** Optional name for logging which section crashed */
  context?: string
}

interface State {
  hasError: boolean
  error: Error | null
}

// ErrorBoundary must be a class component (React limitation).
// Exempt from React Compiler optimization — acceptable since it has minimal render logic.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    errorLogger.capture(error, {
      component: info.componentStack ?? undefined,
      section: this.props.context,
    })
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <ErrorFallback
          level={this.props.level}
          onReset={this.handleReset}
        />
      )
    }
    return this.props.children
  }
}
