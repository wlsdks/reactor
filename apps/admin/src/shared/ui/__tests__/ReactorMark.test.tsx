import { describe, expect, it } from 'vitest'
import { render, screen } from '../../../test/utils'
import { ReactorMark } from '../ReactorMark'

describe('ReactorMark', () => {
  it('uses the reactor-vessel geometry without atomic orbit ellipses', () => {
    const { container } = render(<ReactorMark label="Reactor" />)

    expect(screen.getByRole('img', { name: 'Reactor' })).toBeInTheDocument()
    expect(container.querySelector('ellipse')).not.toBeInTheDocument()
    expect(container.querySelectorAll('circle')).toHaveLength(1)
    expect(container.querySelectorAll('path')).toHaveLength(4)
  })

  it('is decorative when no label is supplied', () => {
    const { container } = render(<ReactorMark />)
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })
})
