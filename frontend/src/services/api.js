const API_BASE_URL = (import.meta.env.VITE_API_URL || (import.meta.env.DEV ? "http://127.0.0.1:5000" : "/api")).replace(/\/$/, "");

async function apiRequest(path, options = {}) {
  const { token: _token, body, headers = {}, ...rest } = options;
  // Tokens stay in HttpOnly cookies; this compatibility option is not transmitted.
  void _token;
  const requestHeaders = { ...headers };
  const isForm = body instanceof FormData;
  if (body !== undefined && !isForm) requestHeaders["Content-Type"] = "application/json";
  const csrf = document.cookie.split("; ").find((value) => value.startsWith("csrf_access_token="))?.split("=").slice(1).join("=");
  if (csrf) requestHeaders["X-CSRF-TOKEN"] = decodeURIComponent(csrf);
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...rest, credentials: "include", headers: requestHeaders,
      ...(body !== undefined ? { body: isForm ? body : JSON.stringify(body) } : {}),
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("Cannot reach the server. Check your connection and try again.", { cause: error });
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && path !== "/users/login" && path !== "/users/register") {
      window.dispatchEvent(new Event("session-ended"));
    }
    const error = new Error(data?.error || data?.message || data?.msg || `Request failed (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return data;
}
const registerUser = (body) => apiRequest("/users/register", { method: "POST", body });
const loginUser = (body) => apiRequest("/users/login", { method: "POST", body });
export { API_BASE_URL, apiRequest, registerUser, loginUser };
