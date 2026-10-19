import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from './AuthContext';

const ProtectedRoute = ({ children }) => {
    const { currentUser, isAuthLoading, currencyReady } = useAuth();

    if (isAuthLoading) {
        return null;
    }

    // If there is no user logged in, intercept the request and redirect to login
    if (!currentUser) {
        return <Navigate to="/" replace />;
    }

    // Wait for the user's currency, so that no amount is shown in the wrong one
    if (!currencyReady) {
        return null;
    }

    // If the user exists, open dashboard
    return children;
};

export default ProtectedRoute;
