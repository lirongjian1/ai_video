/**
 * 前端配置 —— 集中放在这一个文件里，改完即生效，不需要环境变量。
 *
 * 说明：
 *   SUPABASE_ANON_KEY 是 Supabase 的「公开密钥」（Publishable key，
 *   以 sb_publishable_ 开头），它的设计用途就是暴露在前端
 *   （真正保护数据的是数据库 RLS 策略），所以直接写在这里是安全的。
 *
 *   ⚠️ 千万不要把 Secret key（以 sb_secret_ 开头，旧称 service_role）
 *      写在这里 —— 它会绕过所有 RLS，必须只存在于 Supabase 后台。
 *
 * 换项目时：把下面两个值换成你的 Supabase 项目信息即可。
 *   位置：Supabase 后台 → Project Settings → API
 *     Project URL             → 填到 SUPABASE_URL
 *     Publishable key (default) → 填到 SUPABASE_ANON_KEY
 */
export const SUPABASE_URL = 'https://rhwzndrwpylegmkumvbk.supabase.co'

export const SUPABASE_ANON_KEY = 'sb_publishable_MdZFXPHzsb7RffPW_SUPAQ_THLmnExT'
