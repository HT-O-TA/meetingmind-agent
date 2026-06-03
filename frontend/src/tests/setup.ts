import { beforeAll, afterEach, afterAll } from 'vitest'
import '@testing-library/jest-dom'

afterEach(() => {
  // Cleanup after each test
})

beforeAll(() => {
  global.console = {
    ...console,
    log: vi.fn(),
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }
})
