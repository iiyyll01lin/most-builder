interface ProgressBarProps {
  progress: number
  status?: string
  className?: string
}

export function ProgressBar({ progress, status, className = '' }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, progress))
  const isError = progress < 0

  return (
    <div className={`space-y-2 ${className}`}>
      {status && (
        <div className="flex items-center gap-2 text-sm">
          {!isError && clamped < 100 && (
            <span className="inline-block h-2 w-2 animate-ping rounded-full bg-cyan-400" />
          )}
          <span
            className={
              isError
                ? 'text-red-400'
                : clamped === 100
                  ? 'text-green-400'
                  : 'text-cyan-300'
            }
          >
            {status}
          </span>
        </div>
      )}
      <div className="relative h-3 overflow-hidden rounded-full bg-gray-700">
        <div
          className={[
            'h-full rounded-full transition-all duration-500 ease-out',
            isError
              ? 'bg-red-500'
              : clamped === 100
                ? 'bg-green-500'
                : 'bg-gradient-to-r from-cyan-500 to-blue-500',
          ].join(' ')}
          style={{ width: isError ? '100%' : `${clamped}%` }}
          role="progressbar"
          aria-valuenow={isError ? 0 : clamped}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
      {!isError && (
        <p className="text-right text-xs text-gray-500">
          {clamped < 100 ? `${clamped}%` : 'Complete'}
        </p>
      )}
    </div>
  )
}
