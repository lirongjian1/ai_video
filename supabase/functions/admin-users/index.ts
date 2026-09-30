/**
 * admin-users —— 用户管理（仅管理员）
 * action: list | create | update | delete
 * 使用 service_role 操作 auth.users + profiles。
 */
import { adminClient, fail, handler, json, readJson, requireUser } from '../_shared/supabase.ts'

interface Payload {
  action?: string
  user_id?: string
  username?: string
  nickname?: string
  password?: string
  email?: string
  status?: string
  role?: string
}

async function assertAdmin(db: ReturnType<typeof adminClient>, userId: string) {
  const { data } = await db.from('profiles').select('role,status').eq('id', userId).single()
  if (!data || data.role !== 'ADMIN' || data.status !== 'ENABLED') return false
  return true
}

Deno.serve(
  handler(async (req) => {
    const user = await requireUser(req)
    if (!user) return fail('未登录', 401)

    const db = adminClient()
    if (!(await assertAdmin(db, user.id))) return fail('需要管理员权限', 403)

    const payload = await readJson<Payload>(req)
    const action = payload.action ?? 'list'

    if (action === 'list') {
      const { data, error } = await db
        .from('profiles')
        .select('*')
        .order('created_at', { ascending: false })
      if (error) throw new Error(error.message)
      return json({ items: data ?? [], total: data?.length ?? 0 })
    }

    if (action === 'create') {
      if (!payload.email || !payload.password) return fail('缺少邮箱或密码')
      const { data: created, error } = await db.auth.admin.createUser({
        email: payload.email,
        password: payload.password,
        email_confirm: true,
        user_metadata: {
          username: payload.username ?? payload.email.split('@')[0],
          nickname: payload.nickname ?? '',
        },
      })
      if (error) throw new Error(error.message)
      // 触发器已建档，这里补齐 role/status
      await db
        .from('profiles')
        .update({
          role: payload.role ?? 'USER',
          status: payload.status ?? 'ENABLED',
          username: payload.username ?? payload.email.split('@')[0],
          nickname: payload.nickname ?? '',
        })
        .eq('id', created.user.id)
      const { data: profile } = await db.from('profiles').select('*').eq('id', created.user.id).single()
      return json(profile, 201)
    }

    if (action === 'update') {
      if (!payload.user_id) return fail('缺少 user_id')
      const patch: Record<string, unknown> = {}
      if (payload.nickname !== undefined) patch.nickname = payload.nickname
      if (payload.username !== undefined) patch.username = payload.username
      if (payload.status !== undefined) patch.status = payload.status
      if (payload.role !== undefined) patch.role = payload.role
      if (Object.keys(patch).length > 0) {
        const { error } = await db.from('profiles').update(patch).eq('id', payload.user_id)
        if (error) throw new Error(error.message)
      }
      // 密码单独走 auth
      if (payload.password) {
        const { error } = await db.auth.admin.updateUserById(payload.user_id, { password: payload.password })
        if (error) throw new Error(error.message)
      }
      const { data: profile } = await db.from('profiles').select('*').eq('id', payload.user_id).single()
      return json(profile)
    }

    if (action === 'delete') {
      if (!payload.user_id) return fail('缺少 user_id')
      if (payload.user_id === user.id) return fail('不能删除当前登录账号')
      const { error } = await db.auth.admin.deleteUser(payload.user_id)
      if (error) throw new Error(error.message)
      return json({ message: '用户已删除' })
    }

    return fail('未知的 action')
  }),
)
