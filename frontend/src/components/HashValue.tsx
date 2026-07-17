import { useState } from 'react'
import { truncateHash } from '../lib/format'

export function HashValue({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)

  if (!value) {
    return <span className="hash-value__empty">—</span>
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }).catch(() => {/* clipboard unavailable */})
  }

  return (
    <div className="hash-value">
      <span className="hash-value__text" title={value}>
        {truncateHash(value)}
      </span>
      <button
        type="button"
        className={`hash-value__copy${copied ? ' hash-value__copy--copied' : ''}`}
        onClick={handleCopy}
        title={copied ? 'Copied!' : 'Copy to clipboard'}
      >
        {copied ? '✓' : '⎘'}
      </button>
    </div>
  )
}
