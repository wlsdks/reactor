import { useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { OperationButton } from '../../../shared/ui/OperationButton'
import { useAnnouncer } from '../../../shared/ui/LiveAnnouncer'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { probeFaqChannel } from '../api'
import { faqProbeSchema, type FaqProbeFormValues } from '../schema'
import type { FaqProbeResult } from '../types'

interface Props {
  channelId: string
}

export function FaqProbe({ channelId }: Props) {
  const { t } = useTranslation()
  const { announce } = useAnnouncer()
  const queryClient = useQueryClient()
  const resultHeadingRef = useRef<HTMLHeadingElement>(null)
  const [result, setResult] = useState<FaqProbeResult | null>(null)

  const {
    register,
    handleSubmit,
    formState: { errors },
    setError,
  } = useForm<FaqProbeFormValues>({
    resolver: zodResolver(faqProbeSchema),
    defaultValues: { query: '' },
  })

  const mutation = useMutation({
    mutationFn: (values: FaqProbeFormValues) => probeFaqChannel(channelId, values),
    onSuccess: (data) => {
      setResult(data)
      // A probe records a synthetic event that nudges scheduler health
      // (last-probe timestamp). Refresh the scheduler health bar so it does
      // not display a stale "no recent activity" warning after a successful
      // probe.
      queryClient.invalidateQueries({ queryKey: queryKeys.slackFaq.schedulerHealth() })
      const count = data.matches.length
      announce(t('slackFaq.probe.announce', { count }))
      // Defer focus until after the result heading mounts.
      requestAnimationFrame(() => {
        resultHeadingRef.current?.focus()
      })
    },
    onError: (error: unknown) => {
      setError('root', { message: getErrorMessage(error) })
    },
  })

  return (
    <div data-testid="faq-probe">
      <h3>{t('slackFaq.probe.title')}</h3>
      <form onSubmit={handleSubmit((v) => mutation.mutate(v))}>
        {errors.root && (
          <div role="alert" className="form-error">
            {errors.root.message}
          </div>
        )}
        <div className="form-group">
          <label className="form-label" htmlFor="faq-probe-query">
            {t('slackFaq.probe.query')}
            <span className="form-label-required" aria-hidden="true">
              *
            </span>
          </label>
          <textarea
            id="faq-probe-query"
            className="form-input"
            rows={3}
            aria-required="true"
            aria-invalid={!!errors.query}
            aria-describedby={errors.query ? 'faq-probe-query-error' : undefined}
            {...register('query')}
          />
          {errors.query && (
            <span id="faq-probe-query-error" className="form-error" role="alert">
              {errors.query.message}
            </span>
          )}
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="faq-probe-topk">
            {t('slackFaq.probe.topK')}
          </label>
          <input
            id="faq-probe-topk"
            className="form-input"
            type="number"
            min={1}
            max={20}
            step={1}
            aria-invalid={!!errors.topK}
            aria-describedby={errors.topK ? 'faq-probe-topk-error' : undefined}
            {...register('topK', {
              setValueAs: (v) =>
                v === '' || v === undefined || v === null || Number.isNaN(Number(v))
                  ? undefined
                  : Number(v),
            })}
          />
          {errors.topK && (
            <span id="faq-probe-topk-error" className="form-error" role="alert">
              {errors.topK.message}
            </span>
          )}
        </div>
        <OperationButton type="submit" variant="primary" isOperating={mutation.isPending}>
          {t('slackFaq.probe.submit')}
        </OperationButton>
      </form>

      {result && (
        <section className="faq-probe__result" aria-live="polite">
          <h4 ref={resultHeadingRef} tabIndex={-1} data-testid="faq-probe-result-heading">
            {t('slackFaq.probe.resultTitle', { count: result.matches.length })}
          </h4>
          {result.matches.length === 0 ? (
            <p>{t('slackFaq.probe.noMatches')}</p>
          ) : (
            <ol className="faq-probe__matches">
              {result.matches.map((match, idx) => (
                <li key={`${match.faqId}-${idx}`} className="faq-probe__match">
                  <div className="faq-probe__match-title">
                    <span className="mono">{match.faqId}</span> · {match.title}
                  </div>
                  <div
                    className="faq-probe__match-bar"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={1}
                    aria-valuenow={match.confidence}
                    aria-label={t('slackFaq.probe.confidenceAria', {
                      pct: Math.round(match.confidence * 100),
                    })}
                  >
                    <span
                      className="faq-probe__match-bar-fill"
                      style={{ width: `${Math.round(match.confidence * 100)}%` }}
                    />
                  </div>
                  {match.body && <p className="faq-probe__match-body">{match.body}</p>}
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
  )
}
