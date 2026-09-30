/**
 * 共享工具：CORS、Supabase 客户端、统一响应。
 * 所有 Edge Function 复用本模块。
 */
import { createClient, SupabaseClient } from 'jsr:@supabase/supabase-js@2'

export const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers':
    'authorization, x-client-info, apikey, content-type, x-cron-secret',
  'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  })
}

export function fail(message: string, status = 400): Response {
  return json({ detail: message }, status)
}

/** 用 service_role 建客户端，绕过 RLS，供后台任务使用。 */
export function adminClient(): SupabaseClient {
  const url = Deno.env.get('SUPABASE_URL')!
  const key = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
  return createClient(url, key, { auth: { persistSession: false } })
}

/** 用调用者身份建客户端，走 RLS。 */
export function userClient(req: Request): SupabaseClient {
  const url = Deno.env.get('SUPABASE_URL')!
  const anon = Deno.env.get('SUPABASE_ANON_KEY')!
  const authHeader = req.headers.get('Authorization') ?? ''
  return createClient(url, anon, {
    global: { headers: { Authorization: authHeader } },
    auth: { persistSession: false },
  })
}

/** 校验调用者，返回 user 或 null。 */
export async function requireUser(req: Request) {
  const supabase = userClient(req)
  const { data, error } = await supabase.auth.getUser()
  if (error || !data.user) return null
  return data.user
}

export async function readJson<T = Record<string, unknown>>(req: Request): Promise<T> {
  try {
    return (await req.json()) as T
  } catch {
    return {} as T
  }
}

/** Edge Function 入口包装：处理 CORS 预检与统一异常。 */
export function handler(
  fn: (req: Request) => Promise<Response>,
): (req: Request) => Promise<Response> {
  return async (req: Request) => {
    if (req.method === 'OPTIONS') {
      return new Response('ok', { headers: corsHeaders })
    }
    try {
      return await fn(req)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      return fail(message, 500)
    }
  }
}
