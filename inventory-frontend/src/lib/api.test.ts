import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function okJson(data: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
    status: 200,
  })
}

beforeEach(async () => {
  vi.resetModules()
  mockFetch.mockReset()
  mockFetch.mockImplementation(() => okJson({ api_key: 'test-key' }))
})

async function loadApi() {
  const mod = await import('./api')
  return mod.api
}

describe('api.get', () => {
  it('returns parsed JSON on success', async () => {
    const api = await loadApi()
    mockFetch.mockImplementation(() => okJson({ items: [] }))
    const result = await api.get('/po')
    expect(result).toEqual({ items: [] })
  })
})

describe('api.runSync', () => {
  it('sends POST to /run-sync', async () => {
    const api = await loadApi()
    mockFetch.mockImplementation(() => okJson({ status: 'ok' }))
    const result = await api.runSync()
    const postCall = mockFetch.mock.calls.find(
      (c: any[]) => c[0] === '/api/v1/run-sync'
    )
    expect(postCall).toBeDefined()
    expect(postCall![1].method).toBe('POST')
    expect(result).toEqual({ status: 'ok' })
  })
})

describe('api.approvePO', () => {
  it('sends POST with quantity query param', async () => {
    const api = await loadApi()
    mockFetch.mockImplementation(() => okJson({ status: 'approved' }))
    await api.approvePO(42, 100)
    const postCall = mockFetch.mock.calls.find(
      (c: any[]) => typeof c[0] === 'string' && c[0].includes('/po/42/approve')
    )
    expect(postCall).toBeDefined()
    expect(postCall![0]).toContain('quantity=100')
  })

  it('sends POST without quantity when undefined', async () => {
    const api = await loadApi()
    mockFetch.mockImplementation(() => okJson({ status: 'approved' }))
    await api.approvePO(42)
    const postCall = mockFetch.mock.calls.find(
      (c: any[]) => typeof c[0] === 'string' && c[0].includes('/po/42/approve')
    )
    expect(postCall).toBeDefined()
    expect(postCall![0]).not.toContain('quantity')
  })
})

describe('api.rejectPO', () => {
  it('sends POST with reason query param', async () => {
    const api = await loadApi()
    mockFetch.mockImplementation(() => okJson({ status: 'rejected' }))
    await api.rejectPO(5, 'too expensive')
    const postCall = mockFetch.mock.calls.find(
      (c: any[]) => typeof c[0] === 'string' && c[0].includes('/po/5/reject')
    )
    expect(postCall).toBeDefined()
    expect(postCall![0]).toContain('reason=too%20expensive')
  })
})

describe('api.getMetrics', () => {
  it('sends GET with days query param', async () => {
    const api = await loadApi()
    mockFetch.mockImplementation(() => okJson({ acceptance: {}, forecast_error: null }))
    await api.getMetrics(7)
    const getCall = mockFetch.mock.calls.find(
      (c: any[]) => typeof c[0] === 'string' && c[0].includes('/metrics?days=7')
    )
    expect(getCall).toBeDefined()
  })
})
