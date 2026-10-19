import axios from 'axios';
import { notifySessionExpired } from '../utils/sessionEvents';
import { refreshAccessToken } from '../utils/tokenRefresh';
import { API_BASE_URL } from '../utils/apiBase';

// Shared Axios instance — every component imports this to talk to Cam's Django backend.
const axiosClient = axios.create({
    // Base URL from .env — all our API calls automatically prepend this.
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Request Interceptor — automatically attaches our JWT token to every outgoing request.
axiosClient.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('access_token');
        
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// Response Interceptor — if we get a 401, refresh the token and retry the request.
axiosClient.interceptors.response.use(
    (response) => {
        return response;
    },
    async (error) => {
        const originalRequest = error.config;
        const status = error.response?.status;

        if (!originalRequest) return Promise.reject(error);

        if (!error.response || status >= 500) {
            originalRequest._retryCount = (originalRequest._retryCount || 0) + 1;
            if (originalRequest._retryCount <= 3) {
                console.warn(`Backend not ready, retrying request... (${originalRequest._retryCount}/3)`);
                await new Promise(resolve => setTimeout(resolve, 1500));
                return axiosClient(originalRequest);
            }
        }

        const isAuthRequest = originalRequest.url?.includes('/token/')
            || originalRequest.url?.includes('/register/');

        if (status === 401 && !originalRequest._retry && !isAuthRequest) {
            originalRequest._retry = true;
            
            try {
                // Get a new token and retry the original failed request.
                const accessToken = await refreshAccessToken();
                originalRequest.headers.Authorization = `Bearer ${accessToken}`;
                return axiosClient(originalRequest);

            } catch (refreshError) {
                // Let the AuthProvider show the session-expired message and
                // handle navigation, wherever the user currently is.
                notifySessionExpired();
                return Promise.reject(refreshError);
            }
        }

        return Promise.reject(error);
    }
);

export default axiosClient;
