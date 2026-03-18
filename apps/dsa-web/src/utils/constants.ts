const configuredApiBaseUrl = import.meta.env.VITE_API_URL?.trim();

// 預設保持同源 API，避免生產/靜態部署時把請求錯誤打到使用者本機 localhost。
// 僅在顯式提供 VITE_API_URL 時才覆蓋預設行為。
export const API_BASE_URL = configuredApiBaseUrl || '';
