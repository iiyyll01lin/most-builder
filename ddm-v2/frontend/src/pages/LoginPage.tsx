import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { login } from '@/api/auth'
import { useAuthStore } from '@/store/authStore'

export function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const setAuth = useAuthStore((s) => s.setAuth)

  const mutation = useMutation({
    mutationFn: login,
    onSuccess: (data) => {
      setAuth(data.access_token, data.user)
    },
  })

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!username || !password) return
    mutation.mutate({ username, password })
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0a0e1a]">
      <div className="w-full max-w-sm space-y-6 rounded-2xl border border-gray-700 bg-gray-900 p-8">
        <div>
          <h1 className="text-xl font-bold text-gray-100">DDM IE/PE Console</h1>
          <p className="mt-1 text-xs text-gray-500">Manufacturing Execution System</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              autoComplete="username"
              className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:border-cyan-500 focus:outline-none"
              placeholder="engineer"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="w-full rounded-lg border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:border-cyan-500 focus:outline-none"
              placeholder="••••••••"
            />
          </div>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="w-full rounded-lg bg-cyan-600 py-2.5 text-sm font-medium text-white hover:bg-cyan-500 transition-colors disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
          >
            {mutation.isPending ? 'Signing in…' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
