import { createClient } from '@supabase/supabase-js'

import { SUPABASE_ANON_KEY, SUPABASE_URL } from '@/lib/config'

const url = SUPABASE_URL
const anonKey = SUPABASE_ANON_KEY

if (!url || !anonKey || anonKey.startsWith('在这里')) {
  console.warn('[supabase] 请先在 frontend/src/lib/config.ts 里填写 SUPABASE_URL 与 SUPABASE_ANON_KEY')
}

export const supabase = createClient(url ?? '', anonKey ?? '', {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    storageKey: 'ai-video-auth',
  },
})

export const MEDIA_BUCKET = 'media'

/** 把 storage_path 转成可访问的公开 URL。 */
export function publicUrl(storagePath: string | null | undefined): string {
  if (!storagePath) return ''
  const { data } = supabase.storage.from(MEDIA_BUCKET).getPublicUrl(storagePath)
  return data.publicUrl
}

/** 调用 Edge Function，自动带登录态。 */
export async function invokeFunction<T = unknown>(
  name: string,
  body: Record<string, unknown> = {},
): Promise<T> {
  const { data, error } = await supabase.functions.invoke(name, { body })
  if (error) {
    // Edge Function 返回的错误体在 context 里
    const context = (error as unknown as { context?: Response }).context
    if (context) {
      try {
        const payload = await context.clone().json()
        throw new Error(payload.detail || payload.message || error.message)
      } catch (parseError) {
        if (parseError instanceof Error && parseError.message !== 'Unexpected end of JSON input') {
          throw parseError
        }
      }
    }
    throw new Error(error.message)
  }
  return data as T
}

/** 统一错误文案提取。 */
export function errorMessage(error: unknown, fallback = '操作失败'): string {
  if (error instanceof Error) return error.message || fallback
  if (typeof error === 'string') return error
  return fallback
}
