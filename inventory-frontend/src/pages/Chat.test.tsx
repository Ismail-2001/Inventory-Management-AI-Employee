import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import Chat from './Chat'

const mockStreamChat = vi.fn()
const mockGetHistory = vi.fn()
const mockGetConversations = vi.fn()
const mockConfirm = vi.fn()
const mockCancel = vi.fn()

vi.mock('../lib/api', () => ({
  streamChat: (...args: any[]) => mockStreamChat(...args),
  api: {
    getChatHistory: (...args: any[]) => mockGetHistory(...args),
    getChatConversations: (...args: any[]) => mockGetConversations(...args),
    confirmChatAction: (...args: any[]) => mockConfirm(...args),
    cancelChatAction: (...args: any[]) => mockCancel(...args),
  },
}))

vi.mock('../lib/toast', () => ({
  showToast: vi.fn(),
}))

async function typeAndSend(text: string) {
  const textarea = await screen.findByLabelText('Chat message')
  fireEvent.change(textarea, { target: { value: text } })
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))
}

const finalMessageEvent = (overrides: Record<string, unknown> = {}) => ({
  type: 'message',
  conversation_id: 'conv-1',
  content: 'Hello world',
  actions: [],
  tool_trace: [],
  model: 'test-model',
  steps: 2,
  usage: { tokens_in: 10, tokens_out: 5, cost_usd: 0 },
  ...overrides,
})

describe('Chat', () => {
  beforeEach(() => {
    mockStreamChat.mockReset()
    mockGetHistory.mockReset()
    mockGetConversations.mockReset()
    mockConfirm.mockReset()
    mockCancel.mockReset()
    mockGetConversations.mockResolvedValue({ conversations: [] })
    mockGetHistory.mockResolvedValue({ conversation_id: 'conv-1', messages: [] })
  })

  it('renders the empty state with suggestions', async () => {
    render(<Chat />)
    expect(screen.getByText('Ask the Inventory Agent')).toBeInTheDocument()
    expect(await screen.findByText('What should we look at?')).toBeInTheDocument()
    expect(screen.getByText('Which SKUs are below their reorder point?')).toBeInTheDocument()
  })

  it('sends a message and shows the user bubble, then streams the reply', async () => {
    mockStreamChat.mockImplementation(async (_payload: unknown, onEvent: (e: any) => void) => {
      onEvent({ type: 'start', model: 'test-model' })
      onEvent({ type: 'delta', text: 'Hello ' })
      onEvent({ type: 'delta', text: 'world' })
      onEvent({
        type: 'tool',
        name: 'lookup_inventory',
        phase: 'started',
        ok: true,
        summary: '',
        elapsed_ms: 0,
        mutating: false,
      })
      onEvent({
        type: 'tool',
        name: 'lookup_inventory',
        phase: 'finished',
        ok: true,
        summary: '3 items',
        elapsed_ms: 120,
        mutating: false,
      })
      onEvent(finalMessageEvent())
    })

    render(<Chat />)
    await typeAndSend('show me low stock')

    expect(await screen.findByText('show me low stock')).toBeInTheDocument()
    expect(await screen.findByText('Hello world')).toBeInTheDocument()
    expect(screen.getByText(/lookup inventory · 3 items/)).toBeInTheDocument()
    expect(mockStreamChat).toHaveBeenCalledWith(
      { message: 'show me low stock', conversation_id: undefined },
      expect.any(Function),
    )

    await waitFor(() => expect(screen.getByLabelText('Chat message')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Chat message'), { target: { value: 'again' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Send' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await waitFor(() => expect(mockStreamChat).toHaveBeenCalledTimes(2))
    expect(mockStreamChat.mock.calls[1][0]).toEqual({ message: 'again', conversation_id: 'conv-1' })
  })

  it('renders an action card and confirms it', async () => {
    const action = {
      id: 'act-1',
      tool: 'draft_purchase_order',
      status: 'pending',
      created_at: '2026-10-04T10:00:00Z',
      expires_at: '2026-10-04T10:15:00Z',
      params: {
        sku_id: 7,
        sku_code: 'SKU-1001',
        quantity: 50,
        unit_cost: 10,
        total_cost: 500,
        reasoning: 'Below reorder point',
      },
    }
    mockStreamChat.mockImplementation(async (_payload: unknown, onEvent: (e: any) => void) => {
      onEvent(finalMessageEvent({ content: 'Draft a PO for you.', actions: [action] }))
    })
    mockConfirm.mockResolvedValue({ status: 'confirmed', po_id: 42, po_status: 'pending_approval' })

    render(<Chat />)
    await typeAndSend('draft a po')

    expect(await screen.findByTestId('chat-action-card')).toBeInTheDocument()
    expect(screen.getByText('SKU-1001')).toBeInTheDocument()
    expect(screen.getByText('$500.00')).toBeInTheDocument()
    expect(screen.getByText('Below reorder point')).toBeInTheDocument()
    expect(screen.getByText('pending')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Confirm/ }))

    await waitFor(() => expect(mockConfirm).toHaveBeenCalledWith('act-1', 'conv-1'))
    expect(await screen.findByText('PO #42 created — pending approval')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('button', { name: /Confirm/ })).toBeNull())
    const { showToast } = await import('../lib/toast')
    expect(vi.mocked(showToast)).toHaveBeenCalledWith('PO #42 created — pending approval')
  })

  it('cancels a pending action', async () => {
    const action = {
      id: 'act-2',
      tool: 'draft_purchase_order',
      status: 'pending',
      created_at: '2026-10-04T10:00:00Z',
      expires_at: '2026-10-04T10:15:00Z',
      params: { sku_id: 7, sku_code: 'SKU-1001', quantity: 50, unit_cost: 10, total_cost: 500 },
    }
    mockStreamChat.mockImplementation(async (_payload: unknown, onEvent: (e: any) => void) => {
      onEvent(finalMessageEvent({ content: 'Draft a PO for you.', actions: [action] }))
    })
    mockCancel.mockResolvedValue({ status: 'cancelled', action_id: 'act-2' })

    render(<Chat />)
    await typeAndSend('draft a po')

    expect(await screen.findByTestId('chat-action-card')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Cancel/ }))

    await waitFor(() => expect(mockCancel).toHaveBeenCalledWith('act-2', 'conv-1'))
    expect(await screen.findByText('cancelled')).toBeInTheDocument()
  })

  it('shows an error message when the stream fails', async () => {
    mockStreamChat.mockRejectedValue(new Error('agent unavailable'))

    render(<Chat />)
    await typeAndSend('hello')

    expect(await screen.findByText('agent unavailable')).toBeInTheDocument()
  })
})
