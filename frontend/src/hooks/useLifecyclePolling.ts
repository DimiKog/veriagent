import { useCallback, useEffect, useEffectEvent, useRef, useState } from 'react'
import { getEventLifecycleStatus } from '../api/client'
import { errorMessage } from '../lib/format'
import type { EventLifecycleStatusResponse, SectionStatus } from '../types'

const LIFECYCLE_POLL_INTERVAL_MS = 3000

export function useLifecyclePolling(
  onStatus?: (status: EventLifecycleStatusResponse) => void,
) {
  const [trackedEventId, setTrackedEventId] = useState<string | null>(null)
  const [lifecyclePollKey, setLifecyclePollKey] = useState(0)
  const [lifecycleStatus, setLifecycleStatus] =
    useState<EventLifecycleStatusResponse | null>(null)
  const [lifecycleFetchStatus, setLifecycleFetchStatus] = useState<SectionStatus>({
    kind: 'idle',
  })
  const pollGenerationRef = useRef(0)
  const onStatusEvent = useEffectEvent((status: EventLifecycleStatusResponse) => {
    onStatus?.(status)
  })

  const lifecyclePolling = Boolean(trackedEventId) && !lifecycleStatus?.anchored

  const startPolling = useCallback((eventId: string) => {
    const trimmed = eventId.trim()
    if (!trimmed) {
      setLifecycleFetchStatus({
        kind: 'error',
        message: 'Enter an event_id to check its lifecycle.',
      })
      return
    }
    setLifecycleStatus(null)
    setTrackedEventId(trimmed)
    setLifecyclePollKey((key) => key + 1)
    setLifecycleFetchStatus({
      kind: 'loading',
      message: 'Polling event lifecycle status…',
    })
  }, [])

  const stopPolling = useCallback(() => {
    setTrackedEventId(null)
  }, [])

  useEffect(() => {
    if (!trackedEventId) {
      return
    }

    const generation = ++pollGenerationRef.current
    let cancelled = false
    let timerId: ReturnType<typeof setTimeout> | undefined
    const eventId = trackedEventId

    const scheduleNext = () => {
      timerId = setTimeout(() => {
        void pollOnce()
      }, LIFECYCLE_POLL_INTERVAL_MS)
    }

    async function pollOnce() {
      if (cancelled || pollGenerationRef.current !== generation) return

      try {
        const status = await getEventLifecycleStatus(eventId)
        if (cancelled || pollGenerationRef.current !== generation) return

        setLifecycleStatus(status)
        onStatusEvent(status)
        setLifecycleFetchStatus({
          kind: 'success',
          message: status.anchored
            ? 'Event is batched and anchored on-chain.'
            : status.batched
              ? 'Event is batched. Waiting for on-chain anchor…'
              : 'Event submitted. Waiting for batching…',
          data: status,
        })

        if (!status.anchored) {
          scheduleNext()
        }
      } catch (error) {
        if (cancelled || pollGenerationRef.current !== generation) return
        setLifecycleFetchStatus({
          kind: 'error',
          message: `Lifecycle poll failed — retrying. ${errorMessage(error)}`,
        })
        scheduleNext()
      }
    }

    void pollOnce()

    return () => {
      cancelled = true
      if (timerId !== undefined) clearTimeout(timerId)
    }
  }, [trackedEventId, lifecyclePollKey])

  return {
    trackedEventId,
    lifecycleStatus,
    lifecyclePolling,
    lifecycleFetchStatus,
    startPolling,
    stopPolling,
    setLifecycleStatus,
    setLifecycleFetchStatus,
  }
}
