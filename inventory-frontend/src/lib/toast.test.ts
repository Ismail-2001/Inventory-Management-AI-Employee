import { describe, it, expect, vi } from 'vitest'
import { showToast, onToast } from './toast'

describe('toast', () => {
  it('notifies listeners when showToast is called', () => {
    const listener = vi.fn()
    const unsub = onToast(listener)

    showToast('test message')
    expect(listener).toHaveBeenCalledWith('test message')

    unsub()
  })

  it('supports multiple listeners', () => {
    const listener1 = vi.fn()
    const listener2 = vi.fn()
    const unsub1 = onToast(listener1)
    const unsub2 = onToast(listener2)

    showToast('hello')
    expect(listener1).toHaveBeenCalledWith('hello')
    expect(listener2).toHaveBeenCalledWith('hello')

    unsub1()
    unsub2()
  })

  it('unsubscribed listener is not called', () => {
    const listener = vi.fn()
    const unsub = onToast(listener)

    unsub()
    showToast('after unsubscribe')
    expect(listener).not.toHaveBeenCalled()
  })
})
