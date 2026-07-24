import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { findForbiddenPackageScripts } from '../../../scripts/package-script-policy.mjs'

type PackageJson = {
  scripts?: Record<string, string>
}

const packageJson = JSON.parse(
  readFileSync(resolve(process.cwd(), 'package.json'), 'utf8'),
) as PackageJson

describe('package script policy', () => {
  it('keeps lifecycle scripts on pnpm instead of npm or yarn', () => {
    const forbiddenScripts = findForbiddenPackageScripts(packageJson.scripts)
    expect(forbiddenScripts).toEqual([])
  })
})
