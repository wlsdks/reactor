#!/usr/bin/env node
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { findForbiddenPackageScripts } from './package-script-policy.mjs'

const repoRoot = resolve(new URL('..', import.meta.url).pathname)
const packageJson = JSON.parse(readFileSync(resolve(repoRoot, 'package.json'), 'utf8'))
const forbiddenScripts = findForbiddenPackageScripts(packageJson.scripts)

if (forbiddenScripts.length > 0) {
  console.error('Package script policy failed: use pnpm, not npm or yarn.')
  for (const [name, command] of forbiddenScripts) {
    console.error(`- ${name}: ${command}`)
  }
  process.exit(1)
}

console.log('Package script policy passed: lifecycle scripts use pnpm-compatible commands')
