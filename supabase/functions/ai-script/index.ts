/**
 * ai-script —— 生成六段分镜（独立入口，便于前端直接调用）
 * 实际逻辑与 ai-text 的 generate-script 一致，这里做薄封装转发。
 */
import { fail, handler, json, readJson } from '../_shared/supabase.ts'

const TEXT_FN = 'ai-text'

Deno.serve(
  handler(async (req) => {
    const payload = await readJson<Record<string, unknown>>(req)
    const url = `${Deno.env.get('SUPABASE_URL')}/functions/v1/${TEXT_FN}`
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: req.headers.get('Authorization') ?? '',
      },
      body: JSON.stringify({ ...payload, action: 'generate-script' }),
    })
    const data = await response.json().catch(() => ({ detail: '上游返回异常' }))
    if (!response.ok) return json(data, response.status)
    return json(data, response.status)
  }),
)
