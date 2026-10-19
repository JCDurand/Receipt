// Lets plain (non-React) API helpers such as fetchWithAuth notify the
// AuthProvider that the user's session has expired, wherever they currently
// are in the app, without importing React state directly into utils/api.js.
let handler = null;

export const setSessionExpiredHandler = (fn) => {
  handler = fn;
};

export const notifySessionExpired = () => {
  if (handler) handler();
};
