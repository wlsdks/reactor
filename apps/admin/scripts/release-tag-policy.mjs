export const EXPECTED_PACKAGE_VERSION = '1.2.0'

const SEMVER_RELEASE_TAG_PATTERN = /^v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/

export function normalizeRemoteTagRefs(lines) {
  return lines
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split(/\s+/)[1] ?? '')
    .map((ref) => ref.replace(/\^\{\}$/, ''))
    .map((ref) => ref.replace(/^refs\/tags\//, ''))
    .filter((tag) => SEMVER_RELEASE_TAG_PATTERN.test(tag))
    .filter((tag, index, tags) => tags.indexOf(tag) === index)
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
}

export function normalizeLocalTags(tags) {
  return tags
    .map((tag) => tag.trim())
    .filter((tag) => SEMVER_RELEASE_TAG_PATTERN.test(tag))
    .filter((tag, index, allTags) => allTags.indexOf(tag) === index)
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
}

export function evaluateReleaseTagPolicy({ packageVersion, backendVersion, localTags, remoteTags }) {
  const normalizedLocalTags = normalizeLocalTags(localTags)
  const normalizedRemoteTags = normalizeLocalTags(remoteTags)
  const requiredTag = `v${packageVersion}`
  const failures = []

  if (packageVersion !== EXPECTED_PACKAGE_VERSION) {
    failures.push(`package.json version is ${packageVersion}; expected ${EXPECTED_PACKAGE_VERSION}`)
  }

  if (backendVersion !== undefined && backendVersion !== packageVersion) {
    failures.push(`admin version ${packageVersion} does not match backend version ${backendVersion}`)
  }

  if (!normalizedLocalTags.includes(requiredTag)) {
    failures.push(`missing required local release tag: ${requiredTag}`)
  }

  if (!normalizedRemoteTags.includes(requiredTag)) {
    failures.push(`missing required remote release tag: ${requiredTag}`)
  }

  return {
    ok: failures.length === 0,
    failures,
    localTags: normalizedLocalTags,
    remoteTags: normalizedRemoteTags,
    requiredTag,
  }
}
