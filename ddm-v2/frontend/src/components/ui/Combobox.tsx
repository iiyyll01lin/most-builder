import { useState, useEffect } from 'react'

export interface ComboboxOption {
  value: string
  label: string
}

interface ComboboxProps {
  options: ComboboxOption[]
  value: string
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
  className?: string
}

export function Combobox({
  options,
  value,
  onChange,
  placeholder = 'Search…',
  disabled,
  className = '',
}: ComboboxProps) {
  const labelFor = (v: string) => options.find((o) => o.value === v)?.label ?? v

  const [inputValue, setInputValue] = useState(() => labelFor(value))
  const [isOpen, setIsOpen] = useState(false)

  // Sync displayed label when external value or options change
  useEffect(() => {
    setInputValue(labelFor(value))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, options])

  const filtered = inputValue
    ? options.filter(
        (o) =>
          o.label.toLowerCase().includes(inputValue.toLowerCase()) ||
          o.value.toLowerCase().includes(inputValue.toLowerCase()),
      )
    : options

  const handleSelect = (opt: ComboboxOption) => {
    onChange(opt.value)
    setInputValue(opt.label)
    setIsOpen(false)
  }

  const handleBlur = () => {
    // Delay to allow the mousedown on an option to fire first
    setTimeout(() => {
      setIsOpen(false)
      setInputValue(labelFor(value))
    }, 120)
  }

  return (
    <div className={`relative ${className}`}>
      <input
        type="text"
        value={inputValue}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => {
          setInputValue(e.target.value)
          setIsOpen(true)
        }}
        onFocus={() => {
          setInputValue('')
          setIsOpen(true)
        }}
        onBlur={handleBlur}
        className="w-full rounded bg-gray-800 border border-gray-600 px-2 py-1 text-gray-100 text-xs focus:border-cyan-500 focus:outline-none disabled:opacity-50"
      />
      {isOpen && filtered.length > 0 && (
        <ul className="absolute z-50 mt-1 max-h-48 w-full overflow-y-auto rounded border border-gray-600 bg-gray-800 shadow-xl">
          {filtered.slice(0, 60).map((opt) => (
            <li
              key={opt.value}
              onMouseDown={() => handleSelect(opt)}
              className={[
                'cursor-pointer px-3 py-1.5 text-xs transition-colors',
                opt.value === value
                  ? 'bg-cyan-900/60 text-cyan-200'
                  : 'text-gray-200 hover:bg-gray-700',
              ].join(' ')}
            >
              {opt.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
