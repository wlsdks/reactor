#!/usr/bin/env node
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import {
  evaluateReleaseTagPolicy,
  normalizeLocalTags,
  normalizeRemoteTagRefs,
} from './release-tag-policy.mjs'

const repoRoot = resolve(new URL('..', import.meta.url).pathname)
const monorepoRoot = resolve(repoRoot, '../..')
const packageJson = JSON.parse(readFileSync(resolve(repoRoot, 'package.json'), 'utf8'))
const pyproject = readFileSync(resolve(monorepoRoot, 'pyproject.toml'), 'utf8')
const backendVersion = pyproject.match(/^version\s*=\s*"([^"]+)"/m)?.[1]

function git(args) {
  return execFileSync('git', args, { cwd: repoRoot, encoding: 'utf8' }).trim()
}

const localTags = normalizeLocalTags(
  git(['tag', '--list', 'v*', '--sort=v:refname'])
    .split('\n')
    .filter(Boolean),
)

const remoteTags = normalizeRemoteTagRefs(
  git(['ls-remote', '--tags', 'origin', 'v*'])
    .split('\n')
    .filter(Boolean),
)

const result = evaluateReleaseTagPolicy({
  packageVersion: packageJson.version,
  backendVersion,
  localTags,
  remoteTags,
})

if (!result.ok) {
  console.error('Release tag policy failed:')
  for (const failure of result.failures) {
    console.error(`- ${failure}`)
  }
  process.exit(1)
}

console.log(`Release tag policy passed: ${result.requiredTag} covers backend and admin`)
