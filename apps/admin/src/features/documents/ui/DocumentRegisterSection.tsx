import { useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LoadingSpinner } from '../../../shared/ui'
import { ragAnswerProbePath } from '../../../shared/releaseWorkflow'
import type { AddDocumentResponse } from '../types'

interface DocumentRegisterSectionProps {
  onAddDocument: (content: string, metadataRaw: string) => Promise<AddDocumentResponse>
  onBatchAdd: (batchRaw: string) => Promise<void>
}

export function DocumentRegisterSection({ onAddDocument, onBatchAdd }: DocumentRegisterSectionProps) {
  const { t } = useTranslation()
  const [content, setContent] = useState('')
  const [metadataRaw, setMetadataRaw] = useState('{"source":"admin"}')
  const [adding, setAdding] = useState(false)
  const [registeredDocument, setRegisteredDocument] = useState<AddDocumentResponse | null>(null)
  const [verificationQuestion, setVerificationQuestion] = useState('')
  const [batchRaw, setBatchRaw] = useState('[\n  {"content":"Example doc", "metadata":{"source":"batch"}}\n]')
  const [batching, setBatching] = useState(false)
  const [batchCompleted, setBatchCompleted] = useState(false)

  async function handleAddDocument() {
    setAdding(true)
    try {
      const document = await onAddDocument(content, metadataRaw)
      setRegisteredDocument(document)
      setVerificationQuestion('')
      setContent('')
      setMetadataRaw('{"source":"admin"}')
    } finally {
      setAdding(false)
    }
  }

  async function handleBatchAdd() {
    setBatching(true)
    setBatchCompleted(false)
    try {
      await onBatchAdd(batchRaw)
      setBatchCompleted(true)
    } finally {
      setBatching(false)
    }
  }

  return (
    <div className="document-register-workspace">
      <header className="document-register-header">
        <h2>{t('documentsPage.register.title')}</h2>
        <p>{t('documentsPage.register.description')}</p>
      </header>

      <section className="document-register-primary" aria-labelledby="document-register-primary-title">
        <div className="document-register-primary__heading">
          <div>
            <h3 id="document-register-primary-title">{t('documentsPage.register.singleTitle')}</h3>
            <p>{t('documentsPage.register.singleDescription')}</p>
          </div>
        </div>

        <div className="document-register-form">
          <label htmlFor="doc-register-content">
            <span>{t('documentsPage.register.contentLabel')}</span>
            <small>{t('documentsPage.register.contentHint')}</small>
          </label>
          <textarea
            id="doc-register-content"
            rows={10}
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder={t('documentsPage.register.contentPlaceholder')}
          />

          <details className="document-register-advanced">
            <summary>{t('documentsPage.register.advancedMetadata')}</summary>
            <p>{t('documentsPage.register.advancedMetadataDescription')}</p>
            <label htmlFor="doc-register-metadata">{t('documentsPage.metadataJson')}</label>
            <textarea
              id="doc-register-metadata"
              rows={4}
              value={metadataRaw}
              onChange={(event) => setMetadataRaw(event.target.value)}
              spellCheck={false}
            />
          </details>

          <div className="document-register-form__actions">
            <button type="button" className="btn btn-primary" onClick={() => void handleAddDocument()} disabled={adding}>
              {adding ? <LoadingSpinner size="sm" /> : t('documentsPage.register.saveAction')}
            </button>
          </div>
        </div>

        {registeredDocument && (
          <div className="document-register-success" role="status">
            <div>
              <strong>{t('documentsPage.registeredHandoff.title')}</strong>
              <p>{t('documentsPage.registeredHandoff.description')}</p>
            </div>
            <label htmlFor="doc-register-verification-question">
              <span>{t('documentsPage.registeredHandoff.question')}</span>
              <input
                id="doc-register-verification-question"
                value={verificationQuestion}
                onChange={(event) => setVerificationQuestion(event.target.value)}
                placeholder={t('documentsPage.registeredHandoff.placeholder')}
              />
            </label>
            {verificationQuestion.trim() ? (
              <Link
                className="btn btn-secondary"
                to={ragAnswerProbePath({
                  question: verificationQuestion,
                  expectedDocumentId: registeredDocument.id,
                })}
              >
                {t('documentsPage.registeredHandoff.open')}
                <ArrowRight size={14} aria-hidden="true" />
              </Link>
            ) : (
              <button className="btn btn-secondary" type="button" disabled>
                {t('documentsPage.registeredHandoff.open')}
                <ArrowRight size={14} aria-hidden="true" />
              </button>
            )}
            <details>
              <summary>{t('common.technicalDetails')}</summary>
              <dl>
                <div><dt>{t('documentsPage.registeredHandoff.documentId')}</dt><dd>{registeredDocument.id}</dd></div>
              </dl>
            </details>
          </div>
        )}
      </section>

      <details className="document-register-batch">
        <summary>
          <span>{t('documentsPage.register.batchTitle')}</span>
          <small>{t('documentsPage.register.batchDescription')}</small>
        </summary>
        <div className="document-register-batch__content">
          <label htmlFor="doc-batch-json">{t('documentsPage.documentsJsonArray')}</label>
          <textarea
            id="doc-batch-json"
            rows={8}
            value={batchRaw}
            onChange={(event) => setBatchRaw(event.target.value)}
            spellCheck={false}
          />
          <div className="document-register-batch__actions">
            {batchCompleted && <span role="status">{t('documentsPage.register.batchCompleted')}</span>}
            <button type="button" className="btn btn-secondary" onClick={() => void handleBatchAdd()} disabled={batching}>
              {batching ? <LoadingSpinner size="sm" /> : t('documentsPage.register.batchAction')}
            </button>
          </div>
        </div>
      </details>
    </div>
  )
}
