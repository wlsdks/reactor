import { describe, expect, it } from 'vitest'
import {
  resolveReleaseActionRunbookItems,
  resolveReleaseNextActionCommand,
} from '../releaseNextActionCommand'

describe('resolveReleaseNextActionCommand', () => {
  it('uses the explicit command first', () => {
    expect(resolveReleaseNextActionCommand({
      command: ' reactor-admin run ',
      preflightEnvFileCommand: 'preflight',
      releaseSmokeEnvFileCommand: 'smoke',
      remediationCommand: 'remediate',
    })).toBe('reactor-admin run')
  })

  it('falls through release gate command fields in operator order', () => {
    expect(resolveReleaseNextActionCommand({
      command: ' ',
      preflightEnvFileCommand: ' uv run reactor-release-smoke-run --preflight-only ',
      releaseSmokeEnvFileCommand: 'uv run reactor-release-smoke-run',
      remediationCommand: 'uv run remediation',
    })).toBe('uv run reactor-release-smoke-run --preflight-only')

    expect(resolveReleaseNextActionCommand({
      preflightEnvFileCommand: '',
      releaseSmokeEnvFileCommand: ' uv run reactor-release-smoke-run --report-file reports/release-smoke-run.json ',
      remediationCommand: 'uv run remediation',
    })).toBe('uv run reactor-release-smoke-run --report-file reports/release-smoke-run.json')

    expect(resolveReleaseNextActionCommand({
      releaseSmokeEnvFileCommand: ' ',
      remediationCommand: ' uv run reactor-langsmith-eval-sync --preflight-only ',
    })).toBe('uv run reactor-langsmith-eval-sync --preflight-only')
  })

  it('returns null when no runnable command is present', () => {
    expect(resolveReleaseNextActionCommand({
      command: '',
      preflightEnvFileCommand: ' ',
      releaseSmokeEnvFileCommand: null,
      remediationCommand: undefined,
    })).toBeNull()
  })

  it('builds typed runbook command items without collapsing remediation into the primary command', () => {
    expect(resolveReleaseActionRunbookItems({
      command: ' ',
      releaseSmokeEnvFileCommand: ' uv run reactor-release-smoke-run --report-file reports/release-smoke-run.json ',
      remediationCommand: ' uv run reactor-langsmith-eval-sync --preflight-only ',
      envFileCommand: ' printf LANGSMITH_API_KEY=... ',
      releaseReadinessCommand: ' uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json ',
    }, {
      command: 'Run command',
      remediation: 'Remediation command',
      env: 'Env command',
      readiness: 'Readiness command',
    })).toEqual([
      {
        key: 'command',
        label: 'Run command',
        value: 'uv run reactor-release-smoke-run --report-file reports/release-smoke-run.json',
      },
      {
        key: 'remediation',
        label: 'Remediation command',
        value: 'uv run reactor-langsmith-eval-sync --preflight-only',
      },
      {
        key: 'env',
        label: 'Env command',
        value: 'printf LANGSMITH_API_KEY=...',
      },
      {
        key: 'readiness',
        label: 'Readiness command',
        value: 'uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json',
      },
    ])
  })
})
