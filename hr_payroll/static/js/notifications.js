// WebSocket connection for real-time notifications

document.addEventListener('DOMContentLoaded', function () {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // In local dev, we are on port 3000 (Node), but WS is on 8000 (Django).
    // If window.location.port is 3000, swap it to 8000 for WS.
    let host = window.location.host;
    if (window.location.port === '3000') {
        host = window.location.hostname + ':8000';
    }
    const wsUrl = protocol + '//' + host + '/ws/notifications/raw/';

    // Only connect if user is authenticated (can check via template variable or just try)
    // For now, we try to connect. The consumer disconnects anonymous users.

    const notificationSocket = new WebSocket(wsUrl);

    notificationSocket.onopen = function (e) {
        console.log('Notification socket connected');
    };

    notificationSocket.onmessage = function (e) {
        const data = JSON.parse(e.data);
        console.log('Notification received:', data);
        showNotification(data);
    };

    notificationSocket.onclose = function (e) {
        console.error('Notification socket closed unexpectedly. Reconnecting in 3s...');
        setTimeout(function () {
            console.log('Attempting Reconnect...');
            // Reloading page or re-running function would work.
            // For this simple script, a reload is easiest,
            // OR we can wrap the connection logic in a function called connect().
            window.location.reload();
        }, 3000);
    };

    function showNotification(data) {
        // Use Bootstrap Toast or Alert
        // Assuming a container with id 'toast-container' exists
        const toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            // Create container if not exists
            const container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            document.body.appendChild(container); // Append to body
            // Re-select
            // toastContainer = container; // not updating const, but we can use container
            displayToast(container, data);
        } else {
            displayToast(toastContainer, data);
        }
    }

    function displayToast(container, data) {
        const toastId = 'toast-' + data.id;
        const html = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header">
                <strong class="me-auto">${data.title}</strong>
                <small>Just now</small>
                <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">
                ${data.message}
                ${data.link ? `<br><a href="${data.link}">View</a>` : ''}
            </div>
        </div>
        `;

        // Append
        container.insertAdjacentHTML('beforeend', html);

        // Initialize Bootstrap Toast
        const toastEl = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastEl);
        toast.show();
    }
});
