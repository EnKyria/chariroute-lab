import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'

// テストから外部ネットワークに接続しない。各テストは必要な応答を明示的に差し替える。
beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new Error('テストで想定外の fetch が呼ばれました'))),
  )
})

afterEach(() => {
  cleanup()
})
