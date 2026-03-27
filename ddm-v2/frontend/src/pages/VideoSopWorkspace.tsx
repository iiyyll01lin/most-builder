import {
  useRef,
  useState,
  useCallback,
  useEffect,
  useId,
} from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {
  fetchUploads,
  uploadVideo,
  deleteUpload,
  getStreamUrl,
  triggerAnalysis,
  fetchUpload,
} from '@/api/video'
import { VideoPlayer, type VideoPlayerHandle } from '@/components/VideoPlayer'
import { SopActionEditor } from '@/components/SopActionEditor'
import type { SOPVersion } from '@/api/types'

// ─── Props ────────────────────────────────────────────────────────────────────

interface VideoSopWorkspaceProps {
  sop: SOPVersion
  sopQueryKey: unknown[]
  onClose: () => void
}

// ─── VideoSopWorkspace ────────────────────────────────────────────────────────

export function VideoSopWorkspace({ sop, sopQueryKey, onClose }: VideoSopWorkspaceProps) {
  const queryClient = useQueryClient()
  const playerRef = useRef<VideoPlayerHandle>(null)

  // Write currentTime here without re-rendering on every frame.
  const timeRef = useRef<number>(0)

  // Only triggers re-renders on action boundary crossings (~once per step).
  const [activeActionId, setActiveActionId] = useState<string | null>(null)

  // Local analysis polling flag
  const [isPolling, setIsPolling] = useState(false)

  // File input id for accessibility
  const fileInputId = useId()

  // ── Fetch upload list ──────────────────────────────────────────────────────
  const uploadsQuery = useQuery({
    queryKey: ['video-uploads', sop.id],
    queryFn: () => fetchUploads(sop.id!),
    enabled: !!sop.id,
    staleTime: 30_000,
  })

  // Use the first upload if available
  const upload = uploadsQuery.data?.[0]

  // ── Poll upload status while analyzing ────────────────────────────────────
  const pollQuery = useQuery({
    queryKey: ['video-poll', upload?.id],
    queryFn: () => fetchUpload(upload!.id),
    enabled: isPolling && !!upload?.id,
    refetchInterval: 2_000,
    staleTime: 0,
  })

  useEffect(() => {
    const status = pollQuery.data?.status
    if (status === 'analyzed') {
      setIsPolling(false)
      queryClient.invalidateQueries({ queryKey: sopQueryKey })
      queryClient.invalidateQueries({ queryKey: ['video-uploads', sop.id] })
      toast.success('Video analysis complete — AI actions appended to SOP')
    } else if (status === 'failed') {
      setIsPolling(false)
      toast.error(`Analysis failed: ${pollQuery.data?.error_message ?? 'unknown error'}`)
    }
  }, [pollQuery.data?.status, pollQuery.data?.error_message, queryClient, sopQueryKey, sop.id])

  // ── Upload mutation ────────────────────────────────────────────────────────
  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadVideo(sop.id!, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['video-uploads', sop.id] })
      toast.success('Video uploaded successfully')
    },
    onError: () => {
      toast.error('Video upload failed — check file type and size (max 2 GB)')
    },
  })

  // ── Delete mutation ────────────────────────────────────────────────────────
  const deleteMutation = useMutation({
    mutationFn: (uploadId: string) => deleteUpload(uploadId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['video-uploads', sop.id] })
      toast.success('Video removed')
    },
    onError: () => {
      toast.error('Failed to delete video')
    },
  })

  // ── Analyze mutation ──────────────────────────────────────────────────────
  const analyzeMutation = useMutation({
    mutationFn: () => triggerAnalysis(upload!.id),
    onSuccess: (result) => {
      setIsPolling(true)
      toast.success(
        `Analysis started — detected ${result.actions_detected.length} action segment(s). Polling for completion…`,
      )
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof Error ? err.message : 'Analysis request failed'
      toast.error(msg)
    },
  })

  // ── File input handler ────────────────────────────────────────────────────
  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) uploadMutation.mutate(file)
      // Reset so the same file can be re-selected after delete
      e.target.value = ''
    },
    [uploadMutation],
  )

  // ── Video time update → ref (no re-render) ────────────────────────────────
  const handleTimeUpdate = useCallback((t: number) => {
    timeRef.current = t
  }, [])

  // ── rAF loop: detect action boundary crossings ────────────────────────────
  // Only triggers a React state update when the active action ID changes.
  // At 60 fps this is a cheap array find — no re-render on identical result.
  useEffect(() => {
    const timedActions = sop.actions.filter(
      (a) => a.id && a.video_timestamp_start != null,
    )
    if (timedActions.length === 0) return

    let rafId: number
    function tick() {
      const t = timeRef.current
      const active =
        timedActions.find(
          (a) =>
            a.video_timestamp_start! <= t &&
            t <= (a.video_timestamp_end ?? a.video_timestamp_start! + a.seconds),
        ) ?? null

      setActiveActionId((prev) => {
        const next = active?.id ?? null
        return next !== prev ? next : prev
      })
      rafId = requestAnimationFrame(tick)
    }

    rafId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafId)
  }, [sop.actions])

  // ── Seek from table row ───────────────────────────────────────────────────
  const handleSeekRequest = useCallback((seconds: number) => {
    playerRef.current?.seekTo(seconds)
  }, [])

  // ── Derived state ─────────────────────────────────────────────────────────
  const isAnalyzing =
    isPolling ||
    upload?.status === 'processing' ||
    analyzeMutation.isPending

  const canAnalyze =
    upload?.status === 'ready' && !isAnalyzing && sop.status === 'Draft'

  return (
    <div className="min-h-screen bg-[#0a0e1a]">
      {/* Workspace header */}
      <div className="sticky top-0 z-40 flex items-center justify-between gap-4 border-b border-gray-800 bg-gray-900/90 px-5 py-3 backdrop-blur">
        <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            ← Dashboard
          </button>
          <span className="text-gray-700">|</span>
          <span className="text-sm font-semibold text-cyan-400">
            📹 Video · SOP Workspace
          </span>
          <span className="text-xs text-gray-500">v{sop.version_no}</span>
        </div>

        {/* Upload / delete controls */}
        <div className="flex items-center gap-2">
          {!upload && !uploadsQuery.isLoading && (
            <>
              <label
                htmlFor={fileInputId}
                className="cursor-pointer rounded-lg border border-gray-600 bg-gray-800 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-700 transition-colors"
              >
                {uploadMutation.isPending ? '⟳ Uploading…' : '↑ Upload Video'}
              </label>
              <input
                id={fileInputId}
                type="file"
                accept="video/mp4,video/webm,video/avi,video/x-matroska,video/quicktime"
                onChange={handleFileChange}
                disabled={uploadMutation.isPending}
                className="hidden"
              />
            </>
          )}

          {upload && (
            <>
              {/* Analyze button */}
              {canAnalyze && (
                <button
                  onClick={() => analyzeMutation.mutate()}
                  disabled={!canAnalyze}
                  className="rounded-lg border border-purple-700/60 bg-purple-900/30 px-3 py-1.5 text-xs text-purple-300 hover:bg-purple-800/40 transition-colors disabled:opacity-40"
                >
                  ✨ AI Analyze
                </button>
              )}
              {isAnalyzing && (
                <span className="flex items-center gap-1.5 text-xs text-purple-400 animate-pulse">
                  <span className="animate-spin">⟳</span>
                  Analyzing…
                </span>
              )}
              {upload.status === 'analyzed' && (
                <span className="rounded bg-green-900/40 px-2 py-0.5 text-[10px] text-green-400">
                  ✓ Analyzed
                </span>
              )}

              {/* Delete */}
              <button
                onClick={() => {
                  if (confirm('Remove this video from the SOP?')) {
                    deleteMutation.mutate(upload.id)
                  }
                }}
                disabled={deleteMutation.isPending || isAnalyzing}
                className="rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-500 hover:border-red-700/50 hover:text-red-400 transition-colors disabled:opacity-40"
              >
                ✕ Remove
              </button>
            </>
          )}
        </div>
      </div>

      {/* Two-column workspace */}
      <div className="flex gap-0 h-[calc(100vh-53px)]">
        {/* Left column — video player (40%) */}
        <div className="w-[40%] min-w-[320px] border-r border-gray-800 overflow-y-auto p-4 space-y-3">
          {upload && (upload.status === 'ready' || upload.status === 'analyzed') ? (
            <>
              <VideoPlayer
                ref={playerRef}
                src={getStreamUrl(upload.id)}
                onTimeUpdate={handleTimeUpdate}
              />
              <div className="space-y-1 text-xs text-gray-500">
                {upload.original_filename && (
                  <p className="truncate" title={upload.original_filename}>
                    📄 {upload.original_filename}
                  </p>
                )}
                {upload.duration_seconds != null && (
                  <p>
                    ⏱ {upload.duration_seconds.toFixed(1)}s
                    {upload.width != null &&
                      upload.height != null &&
                      ` · ${upload.width}×${upload.height}`}
                    {upload.fps != null && ` · ${upload.fps.toFixed(1)} fps`}
                  </p>
                )}
              </div>

              {/* Timed-action legend */}
              {sop.actions.some((a) => a.video_timestamp_start != null) && (
                <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-3 space-y-1.5">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                    Timed Segments
                  </p>
                  <div className="space-y-1 max-h-48 overflow-y-auto">
                    {sop.actions
                      .filter((a) => a.video_timestamp_start != null)
                      .map((a, i) => (
                        <button
                          key={a.id ?? i}
                          onClick={() => handleSeekRequest(a.video_timestamp_start!)}
                          className={[
                            'flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs transition-colors',
                            a.id === activeActionId
                              ? 'bg-cyan-900/40 text-cyan-300'
                              : 'text-gray-400 hover:bg-gray-800',
                          ].join(' ')}
                        >
                          <span className="font-mono text-[10px] w-10 shrink-0 text-gray-500">
                            {Math.floor(a.video_timestamp_start! / 60)}:
                            {String(Math.floor(a.video_timestamp_start! % 60)).padStart(2, '0')}
                          </span>
                          <span className="truncate">{a.description}</span>
                        </button>
                      ))}
                  </div>
                </div>
              )}
            </>
          ) : upload?.status === 'processing' || upload?.status === 'pending' ? (
            <div className="flex items-center justify-center h-48 rounded-xl border border-dashed border-gray-700">
              <p className="text-xs text-gray-500 animate-pulse">Processing video…</p>
            </div>
          ) : upload?.status === 'failed' ? (
            <div className="flex items-center justify-center h-48 rounded-xl border border-red-700/40 bg-red-950/20">
              <div className="text-center space-y-1">
                <p className="text-xs text-red-400">Video processing failed</p>
                {upload.error_message && (
                  <p className="text-[10px] text-red-600">{upload.error_message}</p>
                )}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-48 rounded-xl border border-dashed border-gray-700 gap-3">
              <p className="text-xs text-gray-600">No video attached to this SOP version</p>
              <label
                htmlFor={fileInputId}
                className="cursor-pointer rounded-lg border border-gray-600 bg-gray-800 px-4 py-2 text-xs text-gray-300 hover:bg-gray-700 transition-colors"
              >
                {uploadMutation.isPending ? '⟳ Uploading…' : '↑ Upload Video'}
              </label>
              <input
                id={fileInputId}
                type="file"
                accept="video/mp4,video/webm,video/avi,video/x-matroska,video/quicktime"
                onChange={handleFileChange}
                disabled={uploadMutation.isPending}
                className="hidden"
              />
            </div>
          )}
        </div>

        {/* Right column — SOP action editor (60%) */}
        <div className="flex-1 overflow-y-auto p-4">
          <SopActionEditor
            sop={sop}
            queryKey={sopQueryKey}
            activeActionId={activeActionId}
            onSeekRequest={handleSeekRequest}
          />
        </div>
      </div>
    </div>
  )
}
