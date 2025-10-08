import { type LabelHTMLAttributes } from 'react'
import classNames from 'classnames'

export type LabelProps = LabelHTMLAttributes<HTMLLabelElement>

export function Label({ className, children, ...props }: LabelProps) {
  return (
    <label
      className={classNames('text-sm font-medium text-slate-600 dark:text-slate-300', className)}
      {...props}
    >
      {children}
    </label>
  )
}
