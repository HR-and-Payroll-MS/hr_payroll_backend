import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import AdminLogin from './AdminLogin';
import { AuthProvider } from './Context/AuthContext';

const container = document.getElementById('root');
if (container) {
    const root = createRoot(container);
    root.render(
        <React.StrictMode>
            <BrowserRouter>
                <AuthProvider>
                    <AdminLogin />
                </AuthProvider>
            </BrowserRouter>
        </React.StrictMode>
    );
}
