import React from 'react';
import clsx from 'clsx';

/**
 * Button Component - Styled button with variants matching HR Dashboard
 * Supports primary, secondary, danger variants and different sizes
 */
export default function Button({
    children,
    variant = 'primary',
    size = 'md',
    disabled = false,
    className,
    ...props
}) {
    const variants = {
        primary: 'bg-primary hover:bg-primary-hover text-white disabled:bg-gray-300',
        secondary: 'bg-gray-200 hover:bg-gray-300 text-gray-900 disabled:bg-gray-100',
        danger: 'bg-red-600 hover:bg-red-700 text-white disabled:bg-red-300',
    };

    const sizes = {
        sm: 'px-3 py-1.5 text-sm',
        md: 'px-4 py-2',
        lg: 'px-6 py-3 text-lg',
    };

    return (
        <button
            className={clsx(
                'rounded-lg font-medium transition-all',
                'focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary',
                'disabled:cursor-not-allowed disabled:opacity-60',
                variants[variant],
                sizes[size],
                className
            )}
            disabled={disabled}
            {...props}
        >
            {children}
        </button>
    );
}
