import { useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { OperationButton } from '../../../shared/ui/OperationButton'
import { useAnnouncer } from '../../../shared/ui/LiveAnnouncer'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { dryRunFaqChannel } from '../api'
import { faqDryRunSchema, type FaqDryRunFormValues } from '../schema'
import type { FaqDryRunResult } from '../types'

interface Props {
  channelId: string
}

export function FaqDryRun({ channelId }: Props) {
  const { t } = useTranslation()
  const { announce } = useAnnouncer()
  const queryClient = useQueryClient()
  const resultHeadingRef = useRef<HTMLHeadingElement>(null)
  const [result, setResult] = useState<FaqDryRunResult | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors },
    setError,
  } = useForm<FaqDryRunFormValues>({
    resolver: zodResolver(faqDryRunSchema),
    defaultValues: { query: '' },
  })

  const mutation = useMutation({
    mutationFn: (values: FaqDryRunFormValues) => dryRunFaqChannel(channelId, values),
    onSuccess: (data) => {
      setResult(data)
      // Mirrors FaqProbe — a dry-run also writes a synthetic activity record
      // that scheduler health uses to compute "last-activity" freshness.
      queryClient.invalidateQueries({ queryKey: queryKeys.slackFaq.schedulerHealth() })
      announce(t('slackFaq.dryRun.announce', { decision: data.decision }))
      requestAnimationFrame(() => {
        resultHeadingRef.current?.focus()
      })
    },
    onError: (error: unknown) => {
      setError('root', { message: getErrorMessage(error) })
    },
  })

  return (
    <div data-testid="faq-dry-run">
      <header className="faq-dry-run__header">
        <h3>{t('slackFaq.dryRun.title')}</h3>
        <p>{t('slackFaq.dryRun.description')}</p>
      </header>
      <form onSubmit={handleSubmit((v) => mutation.mutate(v))}>
        {errors.root && (
          <div role="alert" className="form-error">
            {errors.root.message}
          </div>
        )}
        <div className="form-group">
          <label className="form-label" htmlFor="faq-dryrun-query">
            {t('slackFaq.dryRun.query')}
            <span className="form-label-required" aria-hidden="true">
              *
            </span>
          </label>
          <textarea
            id="faq-dryrun-query"
            className="form-input"
            rows={3}
            aria-required="true"
            aria-invalid={!!errors.query}
            aria-describedby={errors.query ? 'faq-dryrun-query-error' : undefined}
            {...register('query')}
          />
          {errors.query && (
            <span id="faq-dryrun-query-error" className="form-error" role="alert">
              {errors.query.message}
            </span>
          )}
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="faq-dryrun-userid">
            {t('slackFaq.dryRun.userId')}
          </label>
          <input
            id="faq-dryrun-userid"
            className="form-input"
            aria-invalid={!!errors.userId}
            aria-describedby={errors.userId ? 'faq-dryrun-userid-error' : undefined}
            {...register('userId')}
          />
          {errors.userId && (
            <span id="faq-dryrun-userid-error" className="form-error" role="alert">
              {errors.userId.message}
            </span>
          )}
        </div>
        <div className="form-group">
          <label className="form-label form-label--checkbox" htmlFor="faq-dryrun-as-mention">
            <input
              id="faq-dryrun-as-mention"
              type="checkbox"
              {...register('asMention')}
            />
            {t('slackFaq.dryRun.asMention')}
          </label>
        </div>
        <OperationButton type="submit" variant="primary" isOperating={mutation.isPending}>
          {t('slackFaq.dryRun.submit')}
        </OperationButton>
      </form>

      {result && (
        <section className="faq-dry-run__result" aria-live="polite">
          <h4 ref={resultHeadingRef} tabIndex={-1} data-testid="faq-dry-run-result-heading">
            {t('slackFaq.dryRun.resultTitle')}
          </h4>
          <div className="faq-dry-run__decision">
            <strong>{t(`slackFaq.dryRun.decisions.${result.decision}`)}</strong>
          </div>
          {result.reason && <p className="faq-dry-run__reason">{result.reason}</p>}
          {result.match && (
            <div className="faq-dry-run__match" data-testid="faq-dry-run-match">
              <div className="mono">{result.match.faqId}</div>
              <div>{result.match.title}</div>
              <div className="faq-dry-run__match-confidence mono">
                {(result.match.confidence * 100).toFixed(0)}%
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
