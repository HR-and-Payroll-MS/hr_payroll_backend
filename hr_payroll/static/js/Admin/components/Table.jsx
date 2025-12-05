import React from 'react';
import clsx from 'clsx';

/**
 * Table Component - Enhanced table with hover effects and clean styling
 * Matches HR Dashboard table aesthetic
 */
export default function Table({ columns, data, onRowClick, className }) {
    return (
        <div className={clsx('overflow-x-auto rounded-lg border border-gray-200', className)}>
            <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                    <tr>
                        {columns.map((col) => (
                            <th
                                key={col.key}
                                className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                            >
                                {col.label}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                    {data && data.length > 0 ? (
                        data.map((row, idx) => (
                            <tr
                                key={row.id || idx}
                                onClick={() => onRowClick?.(row)}
                                className={clsx(
                                    'hover:bg-gray-50 transition-colors',
                                    onRowClick && 'cursor-pointer'
                                )}
                            >
                                {columns.map((col) => (
                                    <td key={col.key} className="px-6 py-4 text-sm text-gray-900">
                                        {col.render ? col.render(row[col.key], row) : row[col.key]}
                                    </td>
                                ))}
                            </tr>
                        ))
                    ) : (
                        <tr>
                            <td colSpan={columns.length} className="px-6 py-4 text-center text-sm text-gray-500">
                                No data available
                            </td>
                        </tr>
                    )}
                </tbody>
            </table>
        </div>
    );
}
