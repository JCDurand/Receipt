// Trades the stored refresh token for a new access token. The server rotates
// refresh tokens (ROTATE_REFRESH_TOKENS), so the new refresh token it sends
// back is stored as well. Requests which fail together share one refresh
// rather than each sending their own. Resolves with the new access token;
// rejects when the session cannot be renewed, leaving the callers to clear
// the tokens.
import { API_BASE_URL } from './apiBase';

export const clearTokens = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
};

let refreshInProgress = null;

const requestNewTokens = async () => {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) {
    throw new Error('No refresh token available');
  }

  const response = await fetch(`${API_BASE_URL}/token/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh: refreshToken }),
  });

  if (!response.ok) {
    /* Another tab may have refreshed with the same token first, which makes
       this one invalid. The tokens that tab saved are the ones to use. */
    const accessToken = localStorage.getItem('access_token');
    if (accessToken && localStorage.getItem('refresh_token') !== refreshToken) {
      return accessToken;
    }
    throw new Error(`Error ${response.status}: the session could not be refreshed`);
  }

  const tokens = await response.json();
  localStorage.setItem('access_token', tokens.access);
  /* Each refresh token works once: the server sends its replacement. */
  if (tokens.refresh) {
    localStorage.setItem('refresh_token', tokens.refresh);
  }
  return tokens.access;
};

/* Gets a new access token, resolving with it. Requests that find their token
   expired at the same moment share one refresh, since a refresh token cannot be
   used twice. */
export const refreshAccessToken = () => {
  if (!refreshInProgress) {
    refreshInProgress = requestNewTokens().finally(() => {
      refreshInProgress = null;
    });
  }
  return refreshInProgress;
};
