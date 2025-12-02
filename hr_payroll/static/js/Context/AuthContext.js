import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [auth, setAuth] = useState({ user: null });

    const getCookie = (name) => {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    };

    const login = (username, password) => {
        return new Promise((resolve, reject) => {
            // Create a form to submit to Django's login view
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = window.location.pathname; // Submit to current path only

            // Get CSRF token from meta tag first, fallback to cookie
            let csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            if (!csrfToken) {
                csrfToken = getCookie('csrftoken');
            }

            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrfmiddlewaretoken';
            csrfInput.value = csrfToken;
            form.appendChild(csrfInput);

            const userInput = document.createElement('input');
            userInput.type = 'hidden';
            userInput.name = 'username';
            userInput.value = username;
            form.appendChild(userInput);

            const passInput = document.createElement('input');
            passInput.type = 'hidden';
            passInput.name = 'password';
            passInput.value = password;
            form.appendChild(passInput);

            // Preserve the 'next' parameter if it exists in the URL
            const urlParams = new URLSearchParams(window.location.search);
            const nextParam = urlParams.get('next');
            if (nextParam) {
                const nextInput = document.createElement('input');
                nextInput.type = 'hidden';
                nextInput.name = 'next';
                nextInput.value = nextParam;
                form.appendChild(nextInput);
            }

            document.body.appendChild(form);
            form.submit();

            // We don't resolve because the page will reload.
            // If we wanted to handle errors without reload, we'd use fetch/axios,
            // but standard Django Admin login relies on form submission and re-rendering with errors.
        });
    };

    return (
        <AuthContext.Provider value={{ auth, login }}>
            {children}
        </AuthContext.Provider>
    );
};

export default function useAuth() {
    return useContext(AuthContext);
}
