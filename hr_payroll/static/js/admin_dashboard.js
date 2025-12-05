import React from 'react';
import { createRoot } from 'react-dom/client';
import '../css/admin/admin-theme.css';

/**
 * Admin Dashboard Entry Point
 * Renders React-based dashboard for Django admin home page
 */

// Placeholder - will be enhanced with Dashboard component
document.addEventListener('DOMContentLoaded', () => {
    const dashboardRoot = document.getElementById('admin-dashboard-root');

    if (dashboardRoot) {
        const root = createRoot(dashboardRoot);

        // For now, just a simple message
        root.render(
            <div className="p-6">
                <h2 className="text-2xl font-bold text-gray-900">
                    Dashboard Component Coming Soon
                </h2>
                <p className="text-gray-600 mt-2">
                    React-based dashboard will be rendered here
                </p>
            </div>
        );
    }
});
