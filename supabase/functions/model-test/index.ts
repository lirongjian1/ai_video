/**
 * model-test —— 模型连接测试代理
 * 目的：Key 只在服务端使用，前端永远拿不到明文。
 */
import { adminClient, fail, handler, json, readJson, requireUser } from '../_shared/supabase.ts'
import { testModelConnection, type ModelConfig } from '../_shared/gateway.ts'

Deno.serve(
  handler(async (req) => {
    const user = await requireUser(req)
    if (!user) return fail('未登录', 401)

    const payload = await readJson<{ model_config_id?: number }>(req)
    if (!payload.model_config_id) return fail('缺少 model_config_id')

    const db = adminClient()
    const { data: configRow } = await db
      .from('model_configs')
      .select('*')
      .eq('id', payload.model_config_id)
      .single()
    if (!configRow) return fail('模型配置不存在', 404)
    // service_role 绕过 RLS，需自行校验归属
    if (configRow.created_by !== user.id) return fail('模型配置不存在', 404)

    const message = await testModelConnection(configRow as ModelConfig, db, user.id)
    return json({ ok: true, message })
  }),
)
