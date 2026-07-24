import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { i18n, render, screen } from '../../../test/utils'
import { DocumentRegisterSection } from '../ui/DocumentRegisterSection'

describe('DocumentRegisterSection', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'documentsPage.addDocument': 'Add document',
      'documentsPage.content': 'Content',
      'documentsPage.metadataJson': 'Metadata JSON',
      'documentsPage.add': 'Add',
      'documentsPage.batchAdd': 'Batch add',
      'documentsPage.documentsJsonArray': 'Documents JSON array',
      'documentsPage.addBatch': 'Add batch',
      'documentsPage.registeredHandoff.title': 'Verify the indexed document',
      'documentsPage.registeredHandoff.description': 'Ask a question and verify the citation.',
      'documentsPage.registeredHandoff.documentId': 'Document ID',
      'documentsPage.registeredHandoff.question': 'Verification question',
      'documentsPage.registeredHandoff.placeholder': 'Ask about this document...',
      'documentsPage.registeredHandoff.open': 'Open cited answer verification',
      'documentsPage.register.title': 'Register knowledge document',
      'documentsPage.register.description': 'Save guidance and policies used for answers.',
      'documentsPage.register.singleTitle': 'New document',
      'documentsPage.register.singleDescription': 'Register one document and verify it immediately.',
      'documentsPage.register.contentLabel': 'Document content',
      'documentsPage.register.contentHint': 'Use a readable title and paragraphs.',
      'documentsPage.register.contentPlaceholder': 'Enter the document content',
      'documentsPage.register.advancedMetadata': 'Source and additional information',
      'documentsPage.register.advancedMetadataDescription': 'Only add JSON when needed.',
      'documentsPage.register.saveAction': 'Save knowledge document',
      'documentsPage.register.batchTitle': 'Register multiple documents',
      'documentsPage.register.batchDescription': 'Advanced JSON batch registration.',
      'documentsPage.register.batchAction': 'Save document batch',
      'documentsPage.register.batchCompleted': 'Documents saved',
      'common.technicalDetails': 'Technical details',
    }, true, true)
  })

  it('hands a newly registered document to the cited answer probe', async () => {
    const onAddDocument = vi.fn().mockResolvedValue({
      id: 'doc-release-policy',
      content: 'Release policy requires cited evidence.',
      metadata: { source: 'policy://release' },
    })
    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <DocumentRegisterSection onAddDocument={onAddDocument} onBatchAdd={vi.fn()} />
      </MemoryRouter>,
    )

    expect(screen.getByText('Register multiple documents').closest('details')).not.toHaveAttribute('open')
    await user.type(screen.getByLabelText(/Document content/), 'Release policy requires cited evidence.')
    await user.click(screen.getByRole('button', { name: 'Save knowledge document' }))
    await user.type(screen.getByLabelText('Verification question'), 'What does the release policy require?')

    expect(screen.getByText('doc-release-policy')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open cited answer verification' })).toHaveAttribute(
      'href',
      '/rag-cache?tab=rag&question=What+does+the+release+policy+require%3F&expectedDocumentId=doc-release-policy#rag-answer-probe',
    )
  })
})
