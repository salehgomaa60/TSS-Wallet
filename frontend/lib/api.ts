import axios from "axios";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006";

export const api = axios.create({
  baseURL: API_URL,
});

/**
 * Session storage strategy: localStorage
 *
 * localStorage is shared across ALL tabs within the same browser,
 * but is completely isolated between different browsers.
 *
 * Behaviour:
 *   Chrome  (any tab)  → Vault A  (User A logged in)
 *   Firefox (any tab)  → Vault B  (User B logged in)
 *   Edge    (any tab)  → Vault C  (User C logged in)
 *
 * This lets you test transactions between two vaults by using two
 * different browsers simultaneously.
 */
api.interceptors.request.use((config) => {
  // Guard for SSR — localStorage does not exist on the server.
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});
