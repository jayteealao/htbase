import { forwardRef, type SelectHTMLAttributes } from 'react'
import classNames from 'classnames'

export type SelectProps = SelectHTMLAttributes<HTMLSelectElement>

export const Select = forwardRef<HTMLSelectElement, SelectProps>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={classNames(
      'block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-200 disabled:cursor-not-allowed disabled:bg-slate-100',
      className,
    )}
    {...props}
  >
    {children}
  </select>
))

Select.displayName = 'Select'
