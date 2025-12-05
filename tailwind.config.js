/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        './hr_payroll/templates/admin/**/*.html',
        './hr_payroll/static/js/Admin/**/*.{js,jsx}',
    ],
    theme: {
        extend: {
            colors: {
                primary: {
                    DEFAULT: '#16a34a',  // green-600 (from HR Dashboard)
                    hover: '#15803d',     // green-700
                    light: '#dcfce7',     // green-100
                },
            },
        },
    },
    plugins: [],
};
