/**
 * 统一API调用工具函数
 * 标准化错误处理、loading状态、超时控制
 */
import { message } from 'antd';

interface ApiOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: any;
  headers?: Record<string, string>;
  timeout?: number;
  showError?: boolean;
  errorMessage?: string;
}

interface ApiResult<T = any> {
  success: boolean;
  data?: T;
  error?: string;
  status?: number;
}

/**
 * 统一API调用函数
 * @param url API地址（自动添加/api/v1前缀，如果没有的话）
 * @param options 调用选项
 * @returns ApiResult
 */
export async function apiCall<T = any>(
  url: string,
  options: ApiOptions = {}
): Promise<ApiResult<T>> {
  const {
    method = 'GET',
    body,
    headers = {},
    timeout = 30000,
    showError = true,
    errorMessage = 'API调用失败',
  } = options;

  // 自动添加/api/v1前缀
  const fullUrl = url.startsWith('/api/') ? url : `/api/v1/${url}`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(fullUrl, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...headers,
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      const errorText = `${errorMessage}（HTTP ${response.status}）`;
      if (showError) {
        message.warning(errorText);
      }
      return {
        success: false,
        error: errorText,
        status: response.status,
      };
    }

    const data = await response.json();
    return {
      success: true,
      data: data as T,
      status: response.status,
    };
  } catch (error: any) {
    clearTimeout(timeoutId);

    let errorText: string;
    if (error.name === 'AbortError') {
      errorText = `${errorMessage}（请求超时）`;
    } else {
      errorText = `${errorMessage}：${error.message || '未知错误'}`;
    }

    if (showError) {
      message.warning(errorText);
    }

    return {
      success: false,
      error: errorText,
    };
  }
}

/**
 * 简化的GET请求
 */
export async function apiGet<T = any>(
  url: string,
  options?: Omit<ApiOptions, 'method' | 'body'>
): Promise<ApiResult<T>> {
  return apiCall<T>(url, { ...options, method: 'GET' });
}

/**
 * 简化的POST请求
 */
export async function apiPost<T = any>(
  url: string,
  body?: any,
  options?: Omit<ApiOptions, 'method' | 'body'>
): Promise<ApiResult<T>> {
  return apiCall<T>(url, { ...options, method: 'POST', body });
}

/**
 * 简化的PUT请求
 */
export async function apiPut<T = any>(
  url: string,
  body?: any,
  options?: Omit<ApiOptions, 'method' | 'body'>
): Promise<ApiResult<T>> {
  return apiCall<T>(url, { ...options, method: 'PUT', body });
}

/**
 * 简化的DELETE请求
 */
export async function apiDelete<T = any>(
  url: string,
  options?: Omit<ApiOptions, 'method' | 'body'>
): Promise<ApiResult<T>> {
  return apiCall<T>(url, { ...options, method: 'DELETE' });
}
