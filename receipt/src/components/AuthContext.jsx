import React, { createContext, useContext, useEffect, useState } from "react";
import { useLocalStorage } from "../components/useLocalStorage";
import { useNavigate } from "react-router-dom";
import axiosClient from "../api/axiosClient";
import { jwtDecode } from "jwt-decode";
import { setSessionExpiredHandler } from "../utils/sessionEvents";
import { clearTokens, refreshAccessToken } from "../utils/tokenRefresh";
import { documentService } from "../utils/api";
import { setCurrency } from "../utils/format";

const AuthContext = createContext();

const SESSION_EXPIRED_REDIRECT_DELAY_MS = 3000;

const defaultColourScheme = {
    primary: "#5c201d",
    secondary: "#8b3a34",
    accent: "#d4a373",
    background: "#f5f0eb",
    text: "#2d1b1a",
};

// A decoded JWT's `exp` claim is a Unix timestamp in seconds; jwtDecode doesn't
// check it for us, so an expired token still decodes "successfully".
const isTokenExpired = (token) => {
    try {
        const { exp } = jwtDecode(token);
        return !exp || exp * 1000 < Date.now();
    } catch (error) {
        return true;
    }
};

export const AuthProvider = ({ children }) => {
    const [currentUser, setCurrentUser] = useState(null);

    const [isAuthLoading, setIsAuthLoading] = useState(true);
    // Whether the signed-in user has at least one bank account (null = not yet known).
    // Kept here rather than in AccountRequired so it survives route changes and
    // the gate doesn't blank the page while it re-checks on every navigation.
    const [hasAccount, setHasAccount] = useState(null);
    // The currency every figure is reported in, and the ones to choose from.
    // `currencyReady` is false until the user's setting has loaded, so that no
    // page writes an amount in the wrong currency first.
    const [currency, setCurrencyState] = useState("ZAR");
    const [currencies, setCurrencies] = useState([]);
    const [currencyReady, setCurrencyReady] = useState(false);
    const [colourScheme, setColourScheme] = useLocalStorage("colourScheme", defaultColourScheme);
    const [sessionExpired, setSessionExpired] = useState(false);
    const navigate = useNavigate();

    // Registers this provider as the single place any API helper (fetchWithAuth,
    // axiosClient) can report an expired session from, regardless of which page
    // triggered the failing request.
    useEffect(() => {
        setSessionExpiredHandler(() => setSessionExpired(true));
        return () => setSessionExpiredHandler(null);
    }, []);

    useEffect(() => {
        const restoreSession = async () => {
            const accessToken = localStorage.getItem('access_token');
            const refreshToken = localStorage.getItem('refresh_token');

            if (!accessToken || !refreshToken) {
                setCurrentUser(null);
                setIsAuthLoading(false);
                return;
            }

            if (!isTokenExpired(accessToken)) {
                const decoded = jwtDecode(accessToken);
                setCurrentUser({ id: decoded.user_id, ...decoded });
                setIsAuthLoading(false);
                return;
            }

            if (isTokenExpired(refreshToken)) {
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
                setCurrentUser(null);
                setIsAuthLoading(false);
                return;
            }

            try {
                const decoded = jwtDecode(await refreshAccessToken());
                setCurrentUser({ id: decoded.user_id, ...decoded });
            } catch (error) {
                clearTokens();
                setCurrentUser(null);
            } finally {
                setIsAuthLoading(false);
            }
        };

        restoreSession();
    }, []);

    // The token holds only who the user is (their id), so once they are signed in
    // their username and name are fetched, which also covers a restored session.
    useEffect(() => {
        if (!currentUser?.id) return undefined;

        let isMounted = true;
        documentService
            .getProfile()
            .then((profile) => {
                if (!isMounted) return;
                setCurrentUser((prev) => prev && {
                    ...prev,
                    username: profile.username,
                    first_name: profile.first_name,
                    last_name: profile.last_name,
                });
            })
            .catch((error) => console.error("Failed to load the user's profile:", error));

        return () => {
            isMounted = false;
        };
    }, [currentUser?.id]);

    useEffect(() => {
        setHasAccount(null);
        if (!currentUser?.id) return undefined;

        let isMounted = true;
        documentService
            .getAccounts()
            .then((accounts) => {
                if (isMounted) setHasAccount((accounts || []).length > 0);
            })
            .catch((error) => {
                console.error("Failed to check for existing accounts:", error);
                if (isMounted) setHasAccount(false);
            });

        return () => {
            isMounted = false;
        };
    }, [currentUser?.id]);

    useEffect(() => {
        if (!currentUser?.id) {
            setCurrencyReady(false);
            return undefined;
        }

        let isMounted = true;
        documentService
            .getSettings()
            .then((settings) => {
                if (!isMounted) return;
                setCurrency(settings.currency);
                setCurrencyState(settings.currency);
                setCurrencies(settings.currencies || []);
            })
            .catch((error) => console.error("Failed to load the user's settings:", error))
            .finally(() => {
                if (isMounted) setCurrencyReady(true);
            });

        return () => {
            isMounted = false;
        };
    }, [currentUser?.id]);

    // Saves the currency to report in. Resolves once it is in effect, so the
    // caller can reload what it shows (the server converts amounts to it).
    const changeCurrency = async (code) => {
        const settings = await documentService.updateSettings({ currency: code });
        setCurrency(settings.currency);
        setCurrencyState(settings.currency);
        return settings.currency;
    };

    // Sends username + password to Django's /token/ endpoint and stores the JWT tokens.
    const attemptLogin = async (username, password) => {
        try {
            const response = await axiosClient.post('/token/', {
                username,
                password,
            });
            
            // Store both tokens — access for API calls, refresh for when access expires.
            localStorage.setItem('access_token', response.data.access);
            localStorage.setItem('refresh_token', response.data.refresh);
            
            // Decode the JWT to get the user_id
            const decoded = jwtDecode(response.data.access);
            const user = { id: decoded.user_id, username: username, ...decoded }; 
            setCurrentUser(user);
            
            return user;
        } catch (error) {
            console.error("Login failed:", error);
            if (!error.response || error.response.status >= 500) {
                throw new Error("The server is still starting. Please wait a moment and try again.");
            }
            throw new Error("Invalid username or password");
        }
    }

    const logout = () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        setCurrentUser(null);
        setHasAccount(null);
        setSessionExpired(false);
        navigate("/");
    }

    // Once the session-expired message is shown (on whichever page the user
    // was on), log them out after a short delay and send them back to login.
    useEffect(() => {
        if (!sessionExpired) return;
        const timer = setTimeout(() => {
            logout();
        }, SESSION_EXPIRED_REDIRECT_DELAY_MS);
        return () => clearTimeout(timer);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [sessionExpired]);

    return (
        <AuthContext.Provider value={{
            currentUser,
            isAuthLoading,
            hasAccount,
            setHasAccount,
            currency,
            currencies,
            currencyReady,
            changeCurrency,
            colourScheme,
            attemptLogin,
            logout,
        }}
        >
            {sessionExpired && (
                <div className="session-modal-overlay" role="dialog" aria-modal="true">
                    <div className="session-modal">
                        <h2>You have been logged out</h2>
                        <p>Your session has expired. You will be redirected to the registration page.</p>
                    </div>
                </div>
            )}
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    return context;
}