import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from './AuthContext';

// Never wrap /accounts in this: it's where users without an account are sent,
// so gating it would redirect to itself and render nothing.
const AccountRequired = ({ children }) => {
    const { hasAccount } = useAuth();

    if (hasAccount === null) {
        return null;
    }

    if (!hasAccount) {
        return <Navigate to="/accounts" replace />;
    }

    return children;
};

export default AccountRequired;
