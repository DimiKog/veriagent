import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  ADMIN_DEV_AUTH_STORAGE_KEY,
  AGENT_DEV_AUTH_STORAGE_KEY,
  assertDistinctDevAuthStorageKeys,
  clearAdminDevAuthKey,
  clearAgentDevAuthKey,
  readAdminDevAuthKey,
  readAgentDevAuthKey,
  writeAdminDevAuthKey,
  writeAgentDevAuthKey,
} from './devAuthStorage'

class MemorySessionStorage {
  private store = new Map<string, string>()

  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null
  }

  setItem(key: string, value: string): void {
    this.store.set(key, value)
  }

  removeItem(key: string): void {
    this.store.delete(key)
  }
}

describe('devAuthStorage', () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, 'sessionStorage', {
      configurable: true,
      value: new MemorySessionStorage(),
    })
  })

  afterEach(() => {
    clearAdminDevAuthKey()
    clearAgentDevAuthKey()
  })

  it('uses distinct sessionStorage keys for admin and agent credentials', () => {
    assertDistinctDevAuthStorageKeys()
    expect(ADMIN_DEV_AUTH_STORAGE_KEY).not.toBe(AGENT_DEV_AUTH_STORAGE_KEY)
  })

  it('does not let agent key writes overwrite admin key storage', () => {
    writeAdminDevAuthKey('admin-secret')
    writeAgentDevAuthKey('va_agent_test')

    expect(readAdminDevAuthKey()).toBe('admin-secret')
    expect(readAgentDevAuthKey()).toBe('va_agent_test')
  })

  it('does not let admin key writes overwrite agent key storage', () => {
    writeAgentDevAuthKey('va_agent_test')
    writeAdminDevAuthKey('admin-secret')

    expect(readAgentDevAuthKey()).toBe('va_agent_test')
    expect(readAdminDevAuthKey()).toBe('admin-secret')
  })

  it('clears each credential independently', () => {
    writeAdminDevAuthKey('admin-secret')
    writeAgentDevAuthKey('va_agent_test')

    clearAdminDevAuthKey()

    expect(readAdminDevAuthKey()).toBe('')
    expect(readAgentDevAuthKey()).toBe('va_agent_test')
  })
})
