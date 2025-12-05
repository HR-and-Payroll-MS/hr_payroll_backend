import React from 'react';
import clsx from 'clsx';

/**
 * Card Component - Foundation component for all card-based layouts
 * Matches the HR Dashboard aesthetic with clean borders and shadows
 */
export default function Card({ children, className, title, actions }) {
    return (
        <div
            className={clsx(
                'bg-white rounded-lg border border-gray-200',
                'shadow-sm hover:shadow-md transition-shadow',
                className
            )}
        >
            {title && (
                <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
                    <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
                    {actions && <div className="flex items-center space-x-2">{actions}</div>}
                </div>
            )}
            <div className="p-6">{children}</div>
        </div>
    );
}
