#!/usr/bin/env node
/**
 * Verify that every i18n key referenced in source code is present in
 * src/shared/i18n/ko.json.
 *
 * Approach (regex-based, intentionally simple):
 * 1. Walk every .ts / .tsx file under src/, excluding test fixtures and the
 *    locale resource itself.
 * 2. First collect exact locale-key literals from every source file. This
 *    covers safe helpers and configuration tables that receive `t` as an
 *    argument instead of importing i18next themselves.
 * 3. Only scan dynamic `t(...)` calls in files that actually wire up i18next
 *    (`useTranslation` import, `i18n.t(...)` call, or an `i18next` import).
 *    This avoids matching incidental `t('status', value)` calls in unrelated
 *    helpers.
 * 4. Extract `t('key.path')`, `t("key.path")`, `i18n.t('key.path')`,
 *    `i18next.t('key.path')` static-string call sites.
 * 5. Dynamic keys (template literals, identifiers, expressions) are recorded
 *    separately. A template literal's static prefix and source-controlled
 *    locale-key literal protect matching entries from a false unused-key
 *    report; identifiers and computed prefixes remain reported in `--strict`
 *    mode but never fail the run.
 * 5. Compare against the recursively flattened key set from ko.json.
 *
 * Exit codes:
 *   0 - no missing keys and unused keys under threshold
 *   1 - missing keys present, or unused keys exceed threshold
 *   2 - script-level error (file missing, malformed JSON, etc.)
 *
 * CI gate: pass `--strict-unused N` to fail when unused keys exceed N. The
 * default threshold (`UNUSED_THRESHOLD_DEFAULT`) is enforced when no flag is
 * given, so day-to-day `pnpm verify:i18n` runs catch fresh accumulation.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const repoRoot = path.resolve(__dirname, '..')
const SRC_DIR = path.join(repoRoot, 'src')
const KO_PATH = path.join(repoRoot, 'src/shared/i18n/ko.json')

const STRICT = process.argv.includes('--strict')

// Default ceiling for unused keys. It keeps the gate sensitive to fresh stale
// locale data while allowing source-controlled dynamic translation families.
const UNUSED_THRESHOLD_DEFAULT = 300

function parseUnusedThreshold(argv) {
  const flagIdx = argv.indexOf('--strict-unused')
  if (flagIdx === -1) return UNUSED_THRESHOLD_DEFAULT
  const raw = argv[flagIdx + 1]
  const parsed = Number.parseInt(raw ?? '', 10)
  if (!Number.isFinite(parsed) || parsed < 0) {
    console.error(
      `Invalid --strict-unused value: ${raw}. Expected a non-negative integer.`,
    )
    process.exit(2)
  }
  return parsed
}

const UNUSED_THRESHOLD = parseUnusedThreshold(process.argv)

function flattenKeys(obj, prefix = '', acc = new Set()) {
  if (obj == null || typeof obj !== 'object') return acc
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      flattenKeys(value, fullKey, acc)
    } else {
      acc.add(fullKey)
    }
  }
  return acc
}

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name === 'dist' || entry.name === '__tests__' || entry.name === '__mocks__' || entry.name.startsWith('.')) {
      continue
    }
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      walk(full, out)
    } else if (/\.(tsx|ts)$/.test(entry.name) && !/\.(test|spec|stories)\.(tsx|ts)$/.test(entry.name) && !entry.name.endsWith('.d.ts')) {
      out.push(full)
    }
  }
  return out
}

const I18N_IMPORT_RE = /from\s+['"]react-i18next['"]|from\s+['"]i18next['"]|i18n\.t\(|i18next\.t\(/

// Static string keys: t('key'), t("key"), i18n.t('key'), i18next.t('key')
// Negative lookbehind to avoid prefixed identifiers (foot('x'), set('x')) — we
// require either start of token or the property/dot pattern explicitly.
const STATIC_KEY_RE = /(?:^|[^A-Za-z0-9_$.])(?:i18n|i18next)?\.?t\(\s*(['"])([^'"\\]+?)\1/g

// Detects t(`...${expr}...`) or t(variable) — dynamic, not enumerable.
const DYNAMIC_T_RE = /(?:^|[^A-Za-z0-9_$.])(?:i18n|i18next)?\.?t\(\s*([`a-zA-Z_$])/g

// Template literals retain enough source information to preserve the static
// prefix. For example `t(`common.statuses.${status}`)` may legally resolve
// any key under `common.statuses.`; treating every such leaf as dead produces
// a noisy and misleading release gate.
const TEMPLATE_KEY_RE = /(?:^|[^A-Za-z0-9_$.])(?:i18n|i18next)?\.?t\(\s*`([^`\\]*(?:\\.[^`\\]*)*)`/g

// Some safe shared helpers receive a source-controlled key, for example a
// navigation item's `labelKey` or an API error's `i18nKey`, and invoke t() in
// another module. Count exact locale-key string literals so those active
// dispatch tables do not look like dead translations.
const LOCALE_KEY_LITERAL_RE = /(['"])([^'"\\\r\n]+)\1/g

// Heuristic for "this looks like a real i18n key": at least one dot, OR the
// raw token already exists in ko.json. Filters out spurious matches like
// `params.set('status', ...)` patterns that the regex catches.
function looksLikeI18nKey(key, koKeys) {
  if (koKeys.has(key)) return true
  if (key.includes('.')) return true
  return false
}

function extractFromFile(file, koKeys) {
  const source = fs.readFileSync(file, 'utf8')
  const staticKeys = []
  const dynamicSites = []
  const dynamicPrefixes = []

  // Shared formatters and configuration tables can receive `t` as an
  // argument instead of importing i18next themselves. Their exact,
  // source-controlled locale-key literals are still active translations and
  // must be counted before the i18next-import fast path below.
  LOCALE_KEY_LITERAL_RE.lastIndex = 0
  let match
  while ((match = LOCALE_KEY_LITERAL_RE.exec(source)) !== null) {
    const key = match[2]
    if (koKeys.has(key)) staticKeys.push(key)
  }

  if (!I18N_IMPORT_RE.test(source)) {
    return { static: staticKeys, dynamic: dynamicSites, dynamicPrefixes }
  }

  STATIC_KEY_RE.lastIndex = 0
  while ((match = STATIC_KEY_RE.exec(source)) !== null) {
    const key = match[2]
    if (!looksLikeI18nKey(key, koKeys)) continue
    staticKeys.push(key)
  }

  TEMPLATE_KEY_RE.lastIndex = 0
  while ((match = TEMPLATE_KEY_RE.exec(source)) !== null) {
    const template = match[1]
    const expressionIndex = template.indexOf('${')
    if (expressionIndex === -1) {
      if (looksLikeI18nKey(template, koKeys)) staticKeys.push(template)
      continue
    }

    const prefix = template.slice(0, expressionIndex)
    if (prefix.includes('.')) dynamicPrefixes.push(prefix)
  }

  DYNAMIC_T_RE.lastIndex = 0
  while ((match = DYNAMIC_T_RE.exec(source)) !== null) {
    const opener = match[1]
    // Backtick = template literal. Identifier start = variable. Either way dynamic.
    if (opener === '`' || /[a-zA-Z_$]/.test(opener)) {
      // Compute line for nicer reporting
      const before = source.slice(0, match.index)
      const line = before.split('\n').length
      dynamicSites.push({ file, line })
    }
  }

  return { static: staticKeys, dynamic: dynamicSites, dynamicPrefixes }
}

function main() {
  if (!fs.existsSync(KO_PATH)) {
    console.error(`ko.json not found at ${KO_PATH}`)
    process.exit(2)
  }

  let ko
  try {
    ko = JSON.parse(fs.readFileSync(KO_PATH, 'utf8'))
  } catch (err) {
    console.error('Failed to parse ko.json:', err.message)
    process.exit(2)
  }

  const koKeys = flattenKeys(ko)
  const sourceFiles = walk(SRC_DIR)

  const usedKeys = new Set()
  const dynamicSites = []
  const dynamicPrefixes = new Map()
  const keyToFiles = new Map()

  for (const file of sourceFiles) {
    if (file === KO_PATH) continue
    const { static: staticKeys, dynamic, dynamicPrefixes: prefixes } = extractFromFile(file, koKeys)
    for (const key of staticKeys) {
      usedKeys.add(key)
      if (!keyToFiles.has(key)) keyToFiles.set(key, [])
      keyToFiles.get(key).push(path.relative(repoRoot, file))
    }
    for (const site of dynamic) dynamicSites.push(site)
    for (const prefix of prefixes) {
      if (!dynamicPrefixes.has(prefix)) dynamicPrefixes.set(prefix, [])
      dynamicPrefixes.get(prefix).push(path.relative(repoRoot, file))
    }
  }

  for (const [prefix, files] of dynamicPrefixes) {
    for (const key of koKeys) {
      if (!key.startsWith(prefix)) continue
      usedKeys.add(key)
      if (!keyToFiles.has(key)) keyToFiles.set(key, [])
      keyToFiles.get(key).push(...files)
    }
  }

  const missing = [...usedKeys].filter((key) => !koKeys.has(key)).sort()
  const unused = [...koKeys].filter((key) => !usedKeys.has(key)).sort()

  const summary = {
    sourceFiles: sourceFiles.length,
    koKeys: koKeys.size,
    referencedKeys: usedKeys.size,
    missingKeys: missing.length,
    unusedKeys: unused.length,
    dynamicCallSites: dynamicSites.length,
    dynamicKeyPrefixes: dynamicPrefixes.size,
  }
  console.log(JSON.stringify(summary, null, 2))

  if (missing.length > 0) {
    console.error('\nMissing i18n keys (referenced in code but not in ko.json):')
    for (const key of missing) {
      const sample = (keyToFiles.get(key) ?? []).slice(0, 3).join(', ')
      console.error(`- ${key}  [used in: ${sample}]`)
    }
  }

  if (unused.length > 0) {
    console.warn(`\nUnused i18n keys (in ko.json but not referenced in code) — warning only, ${unused.length} key(s):`)
    // Many keys are referenced via dynamic lookups (e.g. `t(\`feature.${id}\`)`).
    // Show the first 20 as a sample so the diff stays readable.
    const sample = unused.slice(0, 20)
    for (const key of sample) console.warn(`- ${key}`)
    if (unused.length > sample.length) {
      console.warn(`  ... and ${unused.length - sample.length} more`)
    }
  }

  if (STRICT && dynamicSites.length > 0) {
    console.warn(`\nDynamic t() call sites (cannot statically verify), ${dynamicSites.length} site(s):`)
    const sample = dynamicSites.slice(0, 20)
    for (const site of sample) {
      console.warn(`- ${path.relative(repoRoot, site.file)}:${site.line}`)
    }
    if (dynamicSites.length > sample.length) {
      console.warn(`  ... and ${dynamicSites.length - sample.length} more`)
    }
  }

  if (missing.length > 0) {
    process.exit(1)
  }

  if (unused.length > UNUSED_THRESHOLD) {
    console.error(
      `\nUnused i18n keys (${unused.length}) exceed threshold (${UNUSED_THRESHOLD}).` +
        ` Prune ko.json or raise --strict-unused / UNUSED_THRESHOLD_DEFAULT in scripts/verify-i18n-keys.mjs.`,
    )
    process.exit(1)
  }
}

main()
