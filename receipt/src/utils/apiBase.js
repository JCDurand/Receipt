/* Where the API is. Set by VITE_API_BASE_URL when it is; otherwise the Django
   dev server while developing, and /api on the same origin in the built app
   (where the frontend's nginx passes /api through to Django). Shared by every
   way the app talks to the API, so they always agree. */
export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "http://localhost:8000/api" : "/api")
).replace(/\/$/, "");
