// Configuration
const CONFIG = {
    serviceWorkerPath: 'static/service-worker.js',
    publicVapidKey: window.ENV.VAPID_PUBLIC_KEY,  // Get from environment
    endpoints: {
        subscribe: (networkId) => `/subscribe/${networkId}`,
        unsubscribe: (networkId) => `/unsubscribe/${networkId}`,
        subscriptions: '/subscriptions'
    }
};
// Global state
let swRegistration = null;
let networkSubscriptions = new Set();

/**
 * Service Worker Initialization
 */
class ServiceWorkerManager {
    static async initialize() {
        if (!this.isSupported()) {
            this.handleUnsupportedBrowser();
            return;
        }

        try {
            swRegistration = await navigator.serviceWorker.register(CONFIG.serviceWorkerPath);
            console.log('Service Worker registered');
            await SubscriptionManager.loadState();
        } catch (error) {
            console.error('Service Worker Error:', error);
        }
    }

    static isSupported() {
        return 'serviceWorker' in navigator && 'PushManager' in window;
    }

    static handleUnsupportedBrowser() {
        console.warn('Push messaging is not supported');
        document.querySelectorAll('.subscribe-btn').forEach(button => {
            button.disabled = true;
            button.textContent = 'Notifications not supported';
        });
    }
}

/**
 * Subscription Management
 */
class SubscriptionManager {
    static async loadState() {
        try {
            const subscription = await swRegistration.pushManager.getSubscription();
            if (subscription) {
                const subscribedNetworks = await this.fetchSubscribedNetworks(subscription);
                networkSubscriptions = new Set(subscribedNetworks);
            }
            UIManager.initialize();
        } catch (error) {
            console.error('Failed to load subscription state:', error);
            UIManager.initialize();
        }
    }

    static async fetchSubscribedNetworks(subscription) {
        const response = await fetch(CONFIG.endpoints.subscriptions, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(subscription)
        });
        return await response.json();
    }

    static async subscribe(button, networkId) {
        try {
            UIManager.setButtonState(button, 'subscribing');
            const subscription = await this.ensureSubscription();
            await this.sendSubscriptionToServer(subscription, networkId);

            networkSubscriptions.add(networkId);
            UIManager.updateButtonState(button, true);
        } catch (error) {
            console.error('Subscribe failed:', error);
            UIManager.handleError(button, 'Subscribe', error);
        }
    }

    static async unsubscribe(button, networkId) {
        try {
            UIManager.setButtonState(button, 'unsubscribing');
            const subscription = await swRegistration.pushManager.getSubscription();

            if (subscription) {
                await this.sendUnsubscriptionToServer(subscription, networkId);
            }

            networkSubscriptions.delete(networkId);
            UIManager.updateButtonState(button, false);
        } catch (error) {
            console.error('Unsubscribe failed:', error);
            UIManager.handleError(button, 'Unsubscribe', error);
        }
    }

    static async ensureSubscription() {
        let subscription = await swRegistration.pushManager.getSubscription();
        if (!subscription) {
            subscription = await swRegistration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this.urlBase64ToUint8Array(CONFIG.publicVapidKey)
            });
        }
        return subscription;
    }

    static async sendSubscriptionToServer(subscription, networkId) {
        const response = await fetch(CONFIG.endpoints.subscribe(networkId), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(subscription)
        });

        if (!response.ok) {
            const result = await response.json();
            throw new Error(result.message || 'Subscription failed');
        }
    }

    static async sendUnsubscriptionToServer(subscription, networkId) {
        const response = await fetch(CONFIG.endpoints.unsubscribe(networkId), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(subscription)
        });

        if (!response.ok) {
            const result = await response.json();
            throw new Error(result.message || 'Unsubscribe failed');
        }
    }

    static urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
            .replace(/\-/g, '+')
            .replace(/_/g, '/');

        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);

        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }
}

/**
 * UI Management
 */
class UIManager {
    static initialize() {
        const subscribeButtons = document.querySelectorAll('.subscribe-btn');
        subscribeButtons.forEach(button => {
            const networkId = button.getAttribute('data-network');
            this.updateButtonState(button, networkSubscriptions.has(networkId));
            button.addEventListener('click', () => this.handleSubscriptionToggle(button, networkId));
        });
    }

    static updateButtonState(button, isSubscribed) {
        button.textContent = isSubscribed ? 'Unsubscribe' : 'Subscribe';
        button.classList.toggle('btn-outline-danger', isSubscribed);
        button.classList.toggle('btn-outline-primary', !isSubscribed);
        button.disabled = false;
    }

    static setButtonState(button, state) {
        button.disabled = true;
        button.textContent = state === 'subscribing' ? 'Subscribing...' : 'Unsubscribing...';
    }

    static handleError(button, action, error) {
        button.textContent = action;
        button.disabled = false;
        alert(error.message || `Failed to ${action.toLowerCase()}. Please try again later.`);
    }

    static async handleSubscriptionToggle(button, networkId) {
        const isSubscribed = networkSubscriptions.has(networkId);
        if (isSubscribed) {
            await SubscriptionManager.unsubscribe(button, networkId);
        } else {
            await SubscriptionManager.subscribe(button, networkId);
        }
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => ServiceWorkerManager.initialize());