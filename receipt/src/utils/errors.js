const collectErrorMessages = (value) => {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.flatMap(collectErrorMessages);
  if (value && typeof value === "object") return Object.values(value).flatMap(collectErrorMessages);
  return [];
};

export const getErrorMessage = (error, fallback) => {
  if (error?.status === 401) return "Your session has expired. Sign in again to continue.";
  if (error?.status >= 500) return "The server couldn't complete that request. Please try again.";
  if (!error?.status) return "Can't reach the server right now. Check your connection and try again.";

  const rawMessage = error.serverMessage || error.message;
  if (!rawMessage) return fallback;

  try {
    const messages = collectErrorMessages(JSON.parse(rawMessage));
    if (messages.length > 0) return messages.join(" ");
  } catch {
    return rawMessage.replace(/^Error \d+:\s*/, "") || fallback;
  }

  return fallback;
};
