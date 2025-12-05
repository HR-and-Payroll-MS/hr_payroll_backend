import React from 'react';
import clsx from 'clsx';

/**
 * Input Component - Styled form input matching HR Dashboard
 * Supports labels, errors, and various input types
 */
export default function Input({
    label,
    error,
    helpText,
    className,
    required = false,
    ...props
}) {
    return (
        <div className="space-y-1">
            {label && (
                <label className="block text-sm font-medium text-gray-700">
                    {label}
                    {required && <span className="text-red-500 ml-1">*</span>}
                </label>
            )}
            <input
                className={clsx(
                    'w-full px-3 py-2 border  rounded-lg transition',
                    'focus:ring-2 focus:ring-primary focus:border-transparent',
                    'placeholder:text-gray-400',
                    error ? 'border-red-500 focus:ring-red-500' : 'border-gray-300',
                    className
                )}
                {...props}
            />
            {helpText && !error && (
                <p className="text-sm text-gray-500">{helpText}</p>
            )}
            {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
    );
}
