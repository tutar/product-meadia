import axios from "axios";

const API_BASE = "http://localhost:8000/api/v1";

const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const isAuthRequest = error.config?.url?.includes("/auth/token") || error.config?.url?.includes("/auth/register");
    if (error.response?.status === 401 && !isAuthRequest) {
      const refresh = localStorage.getItem("refresh_token");
      if (refresh) {
        try {
          const { data } = await axios.post(`${API_BASE}/auth/refresh`, { refresh_token: refresh });
          localStorage.setItem("access_token", data.access_token);
          localStorage.setItem("refresh_token", data.refresh_token);
          error.config.headers.Authorization = `Bearer ${data.access_token}`;
          return axios(error.config);
        } catch {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
        }
      }
    }
    return Promise.reject(error);
  }
);

export default api;
