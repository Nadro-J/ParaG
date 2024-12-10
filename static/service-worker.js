self.addEventListener('push', function(event) {
    if (event.data) {
        const data = JSON.parse(event.data.text());

        const options = {
            body: data.message,
            vibrate: [100, 50, 400],
            data: {
                dateOfArrival: Date.now(),
                primaryKey: '1'
            },
            actions: [
                {
                    action: 'explore',
                    title: 'View Details'
                },
                {
                    action: 'close',
                    title: 'Close'
                }
            ]
        };

        event.waitUntil(
            self.registration.showNotification(`${data.chain} Alert`, options)
        );
    }
});

// Handle notification clicks
self.addEventListener('notificationclick', function(event) {
    event.notification.close();

    if (event.action === 'explore') {
        // Handle the View Details action
        clients.openWindow('/');
    }
});