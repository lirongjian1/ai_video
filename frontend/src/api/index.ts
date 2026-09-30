/**
 * 数据访问层 —— 替代原 axios + FastAPI 接口。
 * 全部走 supabase-js 直连，AI 相关调用走 Edge Function。
 */
import { invokeFunction, supabase } from '@/lib/supabase'
import type {
  AiFile,
  AiTask,
  ApiSecret,
  Character,
  ModelConfig,
  PageResult,
  Project,
  Prompt,
  Scene,
  Script,
  Storyboard,
  User,
} from '@/types'

export { errorMessage, publicUrl } from '@/lib/supabase'

// ------------------------------------------------------------
// 通用分页查询
// ------------------------------------------------------------
interface PageQuery {
  page?: number
  page_size?: number
  keyword?: string
  [key: string]: unknown
}

async function pageQuery<T>(
  table: string,
  options: PageQuery = {},
  searchColumns: string[] = [],
  orderColumn = 'updated_at',
): Promise<PageResult<T>> {
  const page = options.page ?? 1
  const pageSize = options.page_size ?? 20
  const from = (page - 1) * pageSize

  let query = supabase.from(table).select('*', { count: 'exact' })

  if (options.keyword && searchColumns.length > 0) {
    const pattern = `%${String(options.keyword).trim()}%`
    query = query.or(searchColumns.map((column) => `${column}.ilike.${pattern}`).join(','))
  }
  for (const [key, value] of Object.entries(options)) {
    if (['page', 'page_size', 'keyword'].includes(key)) continue
    if (value === undefined || value === null) continue
    query = query.eq(key, value)
  }

  const { data, count, error } = await query
    .order(orderColumn, { ascending: false })
    .range(from, from + pageSize - 1)

  if (error) throw new Error(error.message)
  return {
    items: (data ?? []) as T[],
    total: count ?? 0,
    page,
    page_size: pageSize,
  }
}

// ------------------------------------------------------------
// 项目
// ------------------------------------------------------------
export const projectsApi = {
  list: (params: PageQuery = {}) => pageQuery<Project>('projects', params, ['name', 'description'], 'updated_at'),
  get: async (id: number) => {
    const { data, error } = await supabase.from('projects').select('*').eq('id', id).single()
    if (error) throw new Error(error.message)
    return data as Project
  },
  create: async (payload: Partial<Project>) => {
    const { data: auth } = await supabase.auth.getUser()
    const { data, error } = await supabase
      .from('projects')
      .insert({ ...payload, created_by: auth.user!.id })
      .select()
      .single()
    if (error) throw new Error(error.message)
    return data as Project
  },
  update: async (id: number, payload: Partial<Project>) => {
    const { data, error } = await supabase.from('projects').update(payload).eq('id', id).select().single()
    if (error) throw new Error(error.message)
    return data as Project
  },
  remove: async (id: number) => {
    const { error } = await supabase.from('projects').delete().eq('id', id)
    if (error) throw new Error(error.message)
  },
}

// ------------------------------------------------------------
// 文件 / 资产
// ------------------------------------------------------------
export const filesApi = {
  list: (params: PageQuery = {}) => pageQuery<AiFile>('files', params, ['file_name', 'original_name'], 'created_at'),
  get: async (id: number) => {
    const { data, error } = await supabase.from('files').select('*').eq('id', id).single()
    if (error) throw new Error(error.message)
    return data as AiFile
  },
  /** 上传文件到 Storage 并登记 files 表。 */
  upload: async (file: File, projectId: number | null) => {
    const { data: auth } = await supabase.auth.getUser()
    const fileType = file.type.startsWith('video') ? 'VIDEO' : 'IMAGE'
    const date = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    const ext = file.name.includes('.') ? `.${file.name.split('.').pop()}` : ''
    const storagePath = `uploads/${projectId ?? 'common'}/${date}/${crypto.randomUUID()}${ext}`

    const { error: uploadError } = await supabase.storage
      .from('media')
      .upload(storagePath, file, { contentType: file.type || undefined })
    if (uploadError) throw new Error(`上传失败：${uploadError.message}`)

    const { data, error } = await supabase
      .from('files')
      .insert({
        project_id: projectId,
        file_name: file.name,
        original_name: file.name,
        file_type: fileType,
        mime_type: file.type || 'application/octet-stream',
        file_size: file.size,
        storage_bucket: 'media',
        storage_path: storagePath,
        source_type: 'UPLOAD',
        created_by: auth.user!.id,
      })
      .select()
      .single()
    if (error) throw new Error(error.message)
    return data as AiFile
  },
  /** 登记由浏览器端 MediaBunny 拼接产出的文件。 */
  registerMerged: async (blob: Blob, outputName: string, projectId: number | null) => {
    const { data: auth } = await supabase.auth.getUser()
    const date = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    const storagePath = `generated/video/${date}/${outputName}-${crypto.randomUUID().slice(0, 10)}.mp4`

    const { error: uploadError } = await supabase.storage
      .from('media')
      .upload(storagePath, blob, { contentType: 'video/mp4' })
    if (uploadError) throw new Error(`上传失败：${uploadError.message}`)

    const fileName = storagePath.split('/').pop()!
    const { data, error } = await supabase
      .from('files')
      .insert({
        project_id: projectId,
        file_name: fileName,
        original_name: `${outputName}.mp4`,
        file_type: 'VIDEO',
        mime_type: 'video/mp4',
        file_size: blob.size,
        storage_bucket: 'media',
        storage_path: storagePath,
        source_type: 'VIDEO_MERGE',
        created_by: auth.user!.id,
      })
      .select()
      .single()
    if (error) throw new Error(error.message)
    return data as AiFile
  },
  remove: async (file: AiFile) => {
    await supabase.storage.from('media').remove([file.storage_path])
    const { error } = await supabase.from('files').delete().eq('id', file.id)
    if (error) throw new Error(error.message)
  },
  /** 生成签名 URL（私有文件用）。 */
  signedUrl: async (storagePath: string, expiresIn = 3600) => {
    const { data, error } = await supabase.storage.from('media').createSignedUrl(storagePath, expiresIn)
    if (error) throw new Error(error.message)
    return data.signedUrl
  },
}

// ------------------------------------------------------------
// 模型配置
// ------------------------------------------------------------
export const modelConfigsApi = {
  list: (params: PageQuery = {}) => pageQuery<ModelConfig>('model_configs', params, ['name', 'model_name'], 'updated_at'),
  /** 一次性取全部启用配置，供下拉选择（不分页）。 */
  listAll: async (modelType?: ModelConfig['model_type']) => {
    let query = supabase.from('model_configs').select('*').eq('status', 'ENABLED')
    if (modelType) query = query.eq('model_type', modelType)
    const { data, error } = await query.order('is_default', { ascending: false }).order('id', { ascending: true })
    if (error) throw new Error(error.message)
    return (data ?? []) as ModelConfig[]
  },
  create: async (payload: Partial<ModelConfig>) => {
    const { data: auth } = await supabase.auth.getUser()
    if (payload.is_default) await clearDefault(payload.model_type as string)
    const { data, error } = await supabase
      .from('model_configs')
      .insert({ ...payload, created_by: auth.user!.id })
      .select()
      .single()
    if (error) throw new Error(error.message)
    return data as ModelConfig
  },
  update: async (id: number, payload: Partial<ModelConfig>) => {
    if (payload.is_default && payload.model_type) await clearDefault(payload.model_type, id)
    const { data, error } = await supabase
      .from('model_configs')
      .update(payload)
      .eq('id', id)
      .select()
      .single()
    if (error) throw new Error(error.message)
    return data as ModelConfig
  },
  remove: async (id: number) => {
    const { error } = await supabase.from('model_configs').delete().eq('id', id)
    if (error) throw new Error(error.message)
  },
  test: (id: number) => invokeFunction<{ ok: boolean; message: string }>('model-test', { model_config_id: id }),
}

async function clearDefault(modelType: string, exceptId?: number) {
  let query = supabase.from('model_configs').update({ is_default: false }).eq('model_type', modelType)
  if (exceptId) query = query.neq('id', exceptId)
  await query
}

// ------------------------------------------------------------
// 密钥管理
// 明文只写不读：写入走 save_api_secret，读取只返回掩码。
// ------------------------------------------------------------
export interface SecretPayload {
  id?: number | null
  name: string
  provider?: string
  description?: string | null
  secret_ref: string
  /** 编辑时留空表示不修改原密钥 */
  value?: string | null
  status?: 'ENABLED' | 'DISABLED'
}

export const secretsApi = {
  list: async () => {
    const { data, error } = await supabase.rpc('list_api_secrets')
    if (error) throw new Error(error.message)
    return (data ?? []) as ApiSecret[]
  },
  save: async (payload: SecretPayload) => {
    const { data, error } = await supabase.rpc('save_api_secret', {
      p_id: payload.id ?? null,
      p_name: payload.name,
      p_provider: payload.provider ?? '',
      p_description: payload.description ?? null,
      p_secret_ref: payload.secret_ref,
      p_value: payload.value ?? null,
      p_status: payload.status ?? 'ENABLED',
    })
    if (error) throw new Error(error.message)
    return data as ApiSecret
  },
  remove: async (id: number) => {
    const { data, error } = await supabase.rpc('delete_api_secret', { p_id: id })
    if (error) throw new Error(error.message)
    return data as { message: string }
  },
}

// ------------------------------------------------------------
// 提示词
// ------------------------------------------------------------
export const promptsApi = {
  list: (params: PageQuery = {}) => pageQuery<Prompt>('prompts', params, ['name', 'content'], 'updated_at'),
  create: async (payload: Partial<Prompt>) => {
    const { data: auth } = await supabase.auth.getUser()
    const { data, error } = await supabase
      .from('prompts')
      .insert({ ...payload, created_by: auth.user!.id })
      .select()
      .single()
    if (error) throw new Error(error.message)
    return data as Prompt
  },
  update: async (id: number, payload: Partial<Prompt>) => {
    const { data, error } = await supabase.from('prompts').update(payload).eq('id', id).select().single()
    if (error) throw new Error(error.message)
    return data as Prompt
  },
  remove: async (id: number) => {
    const { error } = await supabase.from('prompts').delete().eq('id', id)
    if (error) throw new Error(error.message)
  },
  generate: (payload: {
    project_id: number | null
    model_config_id: number
    name: string
    keywords: string
    generation_type: string
  }) => invokeFunction<Prompt>('ai-text', { ...payload, action: 'generate-prompt' }),
}

// ------------------------------------------------------------
// 角色 / 场景
// ------------------------------------------------------------
function creativeApi<T>(table: string) {
  return {
    list: (params: PageQuery = {}) => pageQuery<T>(table, params, ['name', 'description'], 'updated_at'),
    create: async (payload: Record<string, unknown>) => {
      const { data: auth } = await supabase.auth.getUser()
      const { data, error } = await supabase
        .from(table)
        .insert({ ...payload, created_by: auth.user!.id })
        .select()
        .single()
      if (error) throw new Error(error.message)
      return data as T
    },
    update: async (id: number, payload: Record<string, unknown>) => {
      const { data, error } = await supabase.from(table).update(payload).eq('id', id).select().single()
      if (error) throw new Error(error.message)
      return data as T
    },
    remove: async (id: number) => {
      const { error } = await supabase.from(table).delete().eq('id', id)
      if (error) throw new Error(error.message)
    },
  }
}

export const charactersApi = creativeApi<Character>('characters')
export const scenesApi = creativeApi<Scene>('scenes')

// ------------------------------------------------------------
// 剧本 / 分镜
// ------------------------------------------------------------
export const scriptsApi = {
  list: async (params: PageQuery = {}): Promise<PageResult<Script>> => {
    const result = await pageQuery<Script>('scripts', params, ['title', 'summary'], 'updated_at')
    // 附上分镜数量
    const { data } = await supabase.from('storyboards').select('script_id')
    const counts = new Map<number, number>()
    for (const row of data ?? []) {
      counts.set(row.script_id, (counts.get(row.script_id) ?? 0) + 1)
    }
    result.items = result.items.map((item) => ({ ...item, storyboard_count: counts.get(item.id) ?? 0 }))
    return result
  },
  create: async (payload: Partial<Script>) => {
    const { data: auth } = await supabase.auth.getUser()
    const { data, error } = await supabase
      .from('scripts')
      .insert({ ...payload, created_by: auth.user!.id })
      .select()
      .single()
    if (error) throw new Error(error.message)
    return data as Script
  },
  update: async (id: number, payload: Partial<Script>) => {
    const { data, error } = await supabase.from('scripts').update(payload).eq('id', id).select().single()
    if (error) throw new Error(error.message)
    // 项目变更时同步分镜归属
    if (payload.project_id) {
      await supabase.from('storyboards').update({ project_id: payload.project_id }).eq('script_id', id)
    }
    return data as Script
  },
  remove: async (id: number) => {
    const { error } = await supabase.from('scripts').delete().eq('id', id)
    if (error) throw new Error(error.message)
  },
  generate: (payload: {
    project_id: number
    model_config_id: number
    title: string
    keywords: string
    style?: string
  }) => invokeFunction<Script>('ai-script', payload),
}

export const storyboardsApi = {
  list: async (params: { script_id?: number; project_id?: number; page_size?: number } = {}) => {
    let query = supabase.from('storyboards').select('*', { count: 'exact' })
    if (params.script_id) query = query.eq('script_id', params.script_id)
    if (params.project_id) query = query.eq('project_id', params.project_id)
    const { data, count, error } = await query
      .order('sequence', { ascending: true })
      .order('id', { ascending: true })
      .limit(params.page_size ?? 100)
    if (error) throw new Error(error.message)
    return { items: (data ?? []) as Storyboard[], total: count ?? 0 }
  },
  create: async (payload: Partial<Storyboard>) => {
    const { data: auth } = await supabase.auth.getUser()
    const { data, error } = await supabase
      .from('storyboards')
      .insert({ ...payload, created_by: auth.user!.id })
      .select()
      .single()
    if (error) throw new Error(error.message)
    return data as Storyboard
  },
  update: async (id: number, payload: Partial<Storyboard>) => {
    const { data, error } = await supabase.from('storyboards').update(payload).eq('id', id).select().single()
    if (error) throw new Error(error.message)
    return data as Storyboard
  },
  remove: async (id: number) => {
    const { error } = await supabase.from('storyboards').delete().eq('id', id)
    if (error) throw new Error(error.message)
  },
}

// ------------------------------------------------------------
// 任务
// ------------------------------------------------------------
export const tasksApi = {
  list: (params: PageQuery = {}) => pageQuery<AiTask>('tasks', params, ['name'], 'id'),
  get: async (id: number) => {
    const { data, error } = await supabase.from('tasks').select('*').eq('id', id).single()
    if (error) throw new Error(error.message)
    return data as AiTask
  },
  cancel: async (id: number) => {
    const { data, error } = await supabase
      .from('tasks')
      .update({ status: 'CANCELLED', finished_at: new Date().toISOString() })
      .eq('id', id)
      .select()
      .single()
    if (error) throw new Error(error.message)
    return data as AiTask
  },
  remove: async (id: number) => {
    const { error } = await supabase.from('tasks').delete().eq('id', id)
    if (error) throw new Error(error.message)
  },
  /** 图片生成走 Edge Function。 */
  generateImage: (payload: {
    prompt_id: number
    model_config_id: number
    project_id?: number | null
    name: string
    size?: string
  }) => invokeFunction<AiFile>('ai-image', payload),
  /** 视频生成：提交后由定时轮询接管。 */
  generateVideo: (payload: {
    storyboard_id: number
    model_config_id: number
    reference_file_ids?: number[]
    duration?: number
    resolution?: string
    seed?: number
  }) => invokeFunction<AiTask>('ai-video-submit', payload),
}

// ------------------------------------------------------------
// 用户管理（管理员）
// ------------------------------------------------------------
export const usersApi = {
  list: () => invokeFunction<{ items: User[]; total: number }>('admin-users', { action: 'list' }),
  create: (payload: { email: string; password: string; username: string; nickname?: string; role?: string }) =>
    invokeFunction<User>('admin-users', { ...payload, action: 'create' }),
  update: (payload: { user_id: string; nickname?: string; status?: string; role?: string; password?: string }) =>
    invokeFunction<User>('admin-users', { ...payload, action: 'update' }),
  remove: (userId: string) => invokeFunction<{ message: string }>('admin-users', { user_id: userId, action: 'delete' }),
}
