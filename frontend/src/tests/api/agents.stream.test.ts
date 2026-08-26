import { afterEach, describe, expect, it, vi } from 'vitest'
import { agentApi } from '@/api/agents'

function streamResponse(chunks: string[], ok = true) {
  const encoder = new TextEncoder()
  const body = new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)))
      controller.close()
    },
  })
  return { ok, status: ok ? 200 : 500, body }
}

describe('agentApi.queryStream', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('解析跨 chunk 的 SSE 事件并在 DONE 结束', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([
      'data: {"type":"phase","data":{"message":"检',
      '索"}}\n\ndata: {"type":"final","data":{"answer":"完成"}}\n\ndata: [DONE]\n\n',
    ]))
    vi.stubGlobal('fetch', fetchMock)
    const events: unknown[] = []

    await agentApi.queryStream({ question: '测试' }, (event) => events.push(event))

    expect(events).toEqual([
      { type: 'phase', data: { message: '检索' } },
      { type: 'final', data: { answer: '完成' } },
    ])
  })

  it('读取没有尾部换行的最后一个事件', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      streamResponse(['data: {"type":"final","data":{"answer":"完成"}}'])
    ))
    const events: unknown[] = []

    await agentApi.queryStream({ question: '测试' }, (event) => events.push(event))

    expect(events).toHaveLength(1)
  })

  it('请求失败时返回明确错误', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streamResponse([], false)))

    await expect(agentApi.queryStream({ question: '测试' }, vi.fn())).rejects.toThrow('500')
  })
})
