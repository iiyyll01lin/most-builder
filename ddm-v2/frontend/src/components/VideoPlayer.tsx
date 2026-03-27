import {
  forwardRef,
  useImperativeHandle,
  useRef,
  useState,
  useCallback,
} from 'react'

// ─── Public handle ────────────────────────────────────────────────────────────

export interface VideoPlayerHandle {
  seekTo(seconds: number): void
  pause(): void
  play(): void
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface VideoPlayerProps {
  /** Streaming URL — supports HTTP Range.  Use getStreamUrl() from api/video. */
  src: string
  /** Called ~4 Hz while playing, and on every seek. */
  onTimeUpdate?: (currentTime: number) => void
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatTime(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

// ─── Component ────────────────────────────────────────────────────────────────

export const VideoPlayer = forwardRef<VideoPlayerHandle, VideoPlayerProps>(
  function VideoPlayer({ src, onTimeUpdate }, ref) {
    const videoRef = useRef<HTMLVideoElement>(null)
    const [isPlaying, setIsPlaying] = useState(false)
    const [currentTime, setCurrentTime] = useState(0)
    const [duration, setDuration] = useState(0)
    const [isReady, setIsReady] = useState(false)
    const [hasError, setHasError] = useState(false)

    // ── Imperative handle ───────────────────────────────────────────────────
    useImperativeHandle(
      ref,
      () => ({
        seekTo(s: number) {
          if (videoRef.current) {
            videoRef.current.currentTime = Math.max(0, s)
          }
        },
        pause() {
          videoRef.current?.pause()
        },
        play() {
          videoRef.current?.play().catch(() => {
            /* Autoplay policy — user must interact first, silently ignored */
          })
        },
      }),
      [],
    )

    // ── Playback events ─────────────────────────────────────────────────────
    const handleTimeUpdate = useCallback(() => {
      const t = videoRef.current?.currentTime ?? 0
      setCurrentTime(t)
      onTimeUpdate?.(t)
    }, [onTimeUpdate])

    const handleLoadedMetadata = useCallback(() => {
      setDuration(videoRef.current?.duration ?? 0)
      setIsReady(true)
      setHasError(false)
    }, [])

    const handlePlay = useCallback(() => setIsPlaying(true), [])
    const handlePause = useCallback(() => setIsPlaying(false), [])
    const handleEnded = useCallback(() => setIsPlaying(false), [])
    const handleError = useCallback(() => setHasError(true), [])

    // ── Controls ────────────────────────────────────────────────────────────
    const togglePlay = useCallback(() => {
      const v = videoRef.current
      if (!v) return
      if (v.paused) {
        v.play().catch(() => {})
      } else {
        v.pause()
      }
    }, [])

    const handleScrub = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        const t = parseFloat(e.target.value)
        if (videoRef.current) {
          videoRef.current.currentTime = t
        }
        setCurrentTime(t)
        onTimeUpdate?.(t)
      },
      [onTimeUpdate],
    )

    return (
      <div className="flex flex-col gap-2 rounded-xl border border-gray-700 bg-gray-900 overflow-hidden">
        {/* Video element */}
        <div className="relative bg-black aspect-video w-full">
          <video
            ref={videoRef}
            src={src}
            className="w-full h-full object-contain"
            preload="metadata"
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={handleLoadedMetadata}
            onPlay={handlePlay}
            onPause={handlePause}
            onEnded={handleEnded}
            onError={handleError}
          />
          {!isReady && !hasError && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/60">
              <span className="text-xs text-gray-400 animate-pulse">Loading video…</span>
            </div>
          )}
          {hasError && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/60">
              <span className="text-xs text-red-400">Failed to load video</span>
            </div>
          )}
        </div>

        {/* Controls bar */}
        <div className="px-3 pb-3 space-y-1.5">
          {/* Scrubber */}
          <input
            type="range"
            min={0}
            max={duration || 1}
            step={0.1}
            value={currentTime}
            onChange={handleScrub}
            disabled={!isReady}
            className="w-full h-1.5 cursor-pointer accent-cyan-500 disabled:opacity-40"
          />

          {/* Play / time */}
          <div className="flex items-center gap-3">
            <button
              onClick={togglePlay}
              disabled={!isReady}
              aria-label={isPlaying ? 'Pause' : 'Play'}
              className="rounded-lg border border-gray-600 bg-gray-800 px-3 py-1 text-xs text-gray-200 hover:bg-gray-700 transition-colors disabled:opacity-40"
            >
              {isPlaying ? '⏸ Pause' : '▶ Play'}
            </button>
            <span className="text-xs font-mono text-gray-400">
              {formatTime(currentTime)}
              {duration > 0 && (
                <span className="text-gray-600"> / {formatTime(duration)}</span>
              )}
            </span>
          </div>
        </div>
      </div>
    )
  },
)
