export function formatModelName(value: string | null | undefined): string {
  const model = value?.trim()
  if (!model) return ''

  const normalized = model.toLowerCase().replace(/[_.:-]+/g, '')
  if (normalized.includes('gpt4o')) return 'GPT-4o'
  if (normalized.includes('gpt35turbo')) return 'GPT-3.5 Turbo'
  if (normalized.includes('claudesonnet')) return 'Claude Sonnet'
  if (normalized.includes('claudehaiku')) return 'Claude Haiku'
  if (normalized.includes('claudeopus')) return 'Claude Opus'
  if (normalized.includes('gemma')) return 'Gemma'
  if (normalized.includes('qwen')) return 'Qwen'

  return model
}
