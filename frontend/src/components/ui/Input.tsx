import { forwardRef, type InputHTMLAttributes } from 'react'
import classNames from 'classnames'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  intent?: 'default' | 'error' | 'success'
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, intent = 'default', ...props }, ref) => {
    return (
      <input
        ref={ref}
        className={classNames(
          'block w-full rounded-lg border bg-white px-3 py-2 text-sm shadow-sm transition focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-200 disabled:cursor-not-allowed disabled:bg-slate-100',
          {
            'border-slate-200 text-slate-900': intent === 'default',
            'border-danger text-danger': intent === 'error',
            'border-success text-success': intent === 'success',
          },
          className,
        )}
        {...props}
      />
    )
  },
)

Input.displayName = 'Input'
