import { afterEach, describe, expect, it, vi } from 'vitest'
import { downloadJsonFile } from './downloadJson'

describe('downloadJsonFile', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('serializes the payload as formatted JSON without transforming keys', () => {
    const click = vi.fn()
    const link = { href: '', download: '', click } as unknown as HTMLAnchorElement
    const documentMock = {
      createElement: vi.fn().mockReturnValue(link),
    }
    vi.stubGlobal('document', documentMock)
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test')
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})

    const payload = {
      batch_id: 'batch-001',
      event_id: 'event-first-run-001',
      proof: [{ sibling: 'abc', side: 'left' as const }],
    }

    downloadJsonFile(payload, 'proof.json')

    expect(documentMock.createElement).toHaveBeenCalledWith('a')
    expect(createObjectURL).toHaveBeenCalled()
    const blob = createObjectURL.mock.calls[0]?.[0] as Blob
    expect(blob.type).toBe('application/json')
    expect(link.download).toBe('proof.json')
    expect(click).toHaveBeenCalled()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test')
  })
})
