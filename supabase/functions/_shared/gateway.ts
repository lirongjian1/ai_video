/**
 * 模型网关 —— ai_gateway.py 的等价迁移。
 * 覆盖：OpenAI 兼容(文本/图片)、ComfyUI、MiniMax、Ark(豆包) 四条协议。
 */

export class ModelCallError extends Error {}

export interface ModelConfig {
  id: number
  name: string
  model_type: 'TEXT' | 'IMAGE' | 'VIDEO'
  provider: string
  base_url: string | null
  model_name: string
  secret_ref: string | null
  extra_config: Record<string, unknown>
  status: string
  is_default: boolean
  /** 归属者（密钥按用户隔离，需要它来定位密钥） */
  created_by?: string | null
}

const KNOWN_ENDPOINT_SUFFIXES = [
  '/chat/completions',
  '/images/generations',
  '/videos/generations',
  '/video_generation',
  '/contents/generations/tasks',
]

function endpointRoot(config: ModelConfig): string {
  const baseUrl = (config.base_url ?? '').trim().replace(/\/+$/, '')
  for (const suffix of KNOWN_ENDPOINT_SUFFIXES) {
    if (baseUrl.toLowerCase().endsWith(suffix)) {
      return baseUrl.slice(0, baseUrl.length - suffix.length)
    }
  }
  return baseUrl
}

function buildUrl(config: ModelConfig, key: string, defaultPath: string): string {
  const baseUrl = (config.base_url ?? '').trim()
  if (!baseUrl) throw new ModelCallError('模型配置缺少接口地址')
  const explicit = config.extra_config?.[key]
  const path = String(explicit ?? defaultPath).trim()
  if (path.startsWith('http://') || path.startsWith('https://')) return path
  const normalizedBase = baseUrl.replace(/\/+$/, '')
  if (explicit == null && normalizedBase.toLowerCase().endsWith(defaultPath.replace(/\/+$/, '').toLowerCase())) {
    return normalizedBase
  }
  return new URL(path.replace(/^\/+/, ''), `${endpointRoot(config).replace(/\/+$/, '')}/`).toString()
}

export function isMiniMaxVideo(config: ModelConfig): boolean {
  if (config.model_type !== 'VIDEO') return false
  const protocol = String(config.extra_config?.protocol ?? '').toUpperCase()
  if (protocol) return protocol === 'MINIMAX'
  const base = (config.base_url ?? '').toLowerCase()
  const model = config.model_name.toLowerCase()
  return (
    base.includes('/minimax/') ||
    base.replace(/\/+$/, '').endsWith('/video_generation') ||
    model.startsWith('minimax-hailuo') ||
    model.startsWith('t2v-') ||
    model.startsWith('i2v-')
  )
}

export function isArkVideo(config: ModelConfig): boolean {
  if (config.model_type !== 'VIDEO') return false
  const protocol = String(config.extra_config?.protocol ?? '').toUpperCase()
  if (protocol) return protocol === 'ARK'
  const base = (config.base_url ?? '').toLowerCase()
  return base.includes('/contents/generations/tasks') || config.model_name.toLowerCase().startsWith('doubao-seedance')
}

export function isComfyUiVideo(config: ModelConfig): boolean {
  if (config.model_type !== 'VIDEO') return false
  const protocol = String(config.extra_config?.protocol ?? '').toUpperCase()
  const base = (config.base_url ?? '').toLowerCase()
  return protocol === 'COMFYUI' || base.includes('/comfyui/comfyui_workflow')
}

function comfyUiUrl(config: ModelConfig, path: string): string {
  const baseUrl = (config.base_url ?? '').trim().replace(/\/+$/, '')
  if (!baseUrl) throw new ModelCallError('模型配置缺少接口地址')
  const marker = '/comfyui/comfyui_workflow'
  const index = baseUrl.toLowerCase().indexOf(marker)
  let root: string
  if (index >= 0) root = baseUrl.slice(0, index + marker.length)
  else if (baseUrl.toLowerCase().endsWith('/api/v1')) root = `${baseUrl}${marker}`
  else root = `${baseUrl}/api/v1${marker}`
  return `${root}/${path.replace(/^\/+/, '')}`
}

function videoUrl(
  config: ModelConfig,
  key: string,
  genericPath: string,
  minimaxPath: string,
  arkPath: string,
  comfyuiPath: string,
): string {
  if (isComfyUiVideo(config) && !config.extra_config?.[key]) {
    const workflowId = String(config.extra_config?.workflow_id ?? config.model_name).trim()
    return comfyUiUrl(config, comfyuiPath.replace('{workflow_id}', workflowId))
  }
  let defaultPath = genericPath
  if (isArkVideo(config)) defaultPath = arkPath
  else if (isMiniMaxVideo(config)) defaultPath = minimaxPath
  return buildUrl(config, key, defaultPath)
}

/** service_role 客户端的最小接口，用于读取数据库中的密钥。 */
export interface SecretDb {
  rpc: (fn: string, args: Record<string, unknown>) => Promise<{ data: unknown }>
}

/** 解析密钥 + 组装请求头（异步，因为要从数据库取密钥）。 */
async function buildHeaders(
  config: ModelConfig,
  db?: SecretDb,
  ownerId?: string,
): Promise<Record<string, string>> {
  const key = await resolveApiKey(config, db, ownerId)
  return headers(config, key)
}

/**
 * 取密钥：从数据库 api_secrets 表解密读取（按归属者查找），回退到环境变量。
 *
 * 密钥按用户隔离，所以必须带上「模型配置的归属者」ownerId。
 * 走 get_api_secret_plain_for(ref, owner) —— 只在该用户名下查找。
 */
export async function resolveApiKey(
  config: ModelConfig,
  db?: SecretDb,
  ownerId?: string,
): Promise<string> {
  const ref = config.secret_ref || `${config.provider.toUpperCase()}_API_KEY`
  if (db) {
    // 优先按归属者查找（密钥按用户隔离）
    const owner = ownerId ?? config.created_by ?? undefined
    if (owner) {
      const { data } = await db.rpc('get_api_secret_plain_for', { p_ref: ref, p_owner: owner })
      if (typeof data === 'string' && data) return data
    }
    // 兼容旧数据：仍尝试旧的全局查找
    const { data: legacy } = await db.rpc('get_api_secret_plain', { p_ref: ref })
    if (typeof legacy === 'string' && legacy) return legacy
  }
  return Deno.env.get(ref) ?? ''
}

function headers(config: ModelConfig, apiKeyValue?: string): Record<string, string> {
  const result: Record<string, string> = {
    Accept: 'application/json',
    'Content-Type': 'application/json',
  }
  const key = apiKeyValue ?? ''
  if (key) {
    const headerName = String(config.extra_config?.auth_header ?? 'Authorization')
    const defaultScheme = isComfyUiVideo(config) ? '' : 'Bearer'
    const scheme = String(config.extra_config?.auth_scheme ?? defaultScheme).trim()
    result[headerName] = `${scheme} ${key}`.trim()
  }
  const extra = config.extra_config?.headers
  if (extra && typeof extra === 'object') {
    for (const [k, v] of Object.entries(extra as Record<string, unknown>)) {
      result[String(k)] = String(v)
    }
  }
  return result
}

function timeoutSeconds(config: ModelConfig, fallback = 120): number {
  const value = Number(config.extra_config?.timeout ?? fallback)
  return Number.isFinite(value) ? value : fallback
}

function pickOptions(config: ModelConfig, key: string): Record<string, unknown> {
  const value = config.extra_config?.[key]
  return value && typeof value === 'object' && !Array.isArray(value) ? { ...(value as Record<string, unknown>) } : {}
}

type NestedPath = (string | number)[]

function nested(payload: unknown, ...paths: NestedPath[]): unknown {
  for (const path of paths) {
    let value: unknown = payload
    try {
      for (const part of path) {
        if (value == null) break
        value = typeof part === 'number' ? (value as unknown[])[part] : (value as Record<string, unknown>)[part]
      }
    } catch {
      value = undefined
    }
    if (value !== undefined && value !== null) return value
  }
  return null
}

function availableModelIds(payload: Record<string, unknown>): Set<string> {
  const items = nested(payload, ['data'], ['models'], ['result', 'data'])
  if (!Array.isArray(items)) return new Set()
  const ids = new Set<string>()
  for (const item of items) {
    if (typeof item === 'string') ids.add(item.trim())
    else if (item && typeof item === 'object') {
      const record = item as Record<string, unknown>
      const value = record.id ?? record.model ?? record.name
      if (value) ids.add(String(value).trim())
    }
  }
  ids.delete('')
  return ids
}

async function parseJson(response: Response): Promise<Record<string, unknown>> {
  // 注意：Response 的 body 只能消费一次，这里统一读出文本再解析
  const text = await response.text().catch(() => '')
  return parseJsonText(response, text)
}

/**
 * 基于已读出的文本解析响应。
 * 与 parseJson 分离，是为了让调用方在需要「先看文本再决定是否解析」时
 * 不必重复读取 response body（body 只能读一次，response.clone() 在部分
 * 边缘运行时不可用）。
 */
function parseJsonText(response: Response, text: string): Record<string, unknown> {
  if (!response.ok) {
    const trimmed = text.trim().slice(-1500)
    let detail = trimmed
    try {
      const errorPayload = JSON.parse(trimmed)
      if (errorPayload && typeof errorPayload === 'object') {
        const message = String(nested(errorPayload, ['error', 'message'], ['message'], ['msg']) ?? '')
        const code = String(nested(errorPayload, ['error', 'code'], ['code']) ?? '')
        const normalized = `${code} ${message}`.toLowerCase()
        if (code === '401008' || (normalized.includes('quota') && normalized.includes('postpaid'))) {
          detail = '模型服务额度已用尽且未开启后付费，请在模型厂商控制台开通计费，或更换有可用额度的 API Key'
        } else if (normalized.includes('sensitive_words_detected')) {
          detail = '模型服务拒绝了当前输入：内容审核未通过，请调整关键词后重试'
        } else if (message.includes('模型未部署或不支持该接口')) {
          detail = '当前模型未部署或不支持该接口，请检查模型名称和接口地址'
        }
      }
    } catch {
      // 保持原始文本
    }
    throw new ModelCallError(`模型接口返回 ${response.status}: ${detail || response.statusText}`)
  }
  try {
    const payload = JSON.parse(text)
    if (!payload || typeof payload !== 'object') throw new Error()
    return payload as Record<string, unknown>
  } catch {
    throw new ModelCallError('模型接口没有返回有效 JSON')
  }
}

async function downloadMedia(url: string, extraHeaders?: Record<string, string>): Promise<[Uint8Array, string]> {
  const response = await fetch(url, { headers: extraHeaders ?? {} })
  if (!response.ok) throw new ModelCallError(`生成结果下载失败：HTTP ${response.status}`)
  const contentType = (response.headers.get('content-type') ?? 'application/octet-stream').split(';')[0]
  return [new Uint8Array(await response.arrayBuffer()), contentType]
}

function decodeBase64(value: string, defaultMime: string): [Uint8Array, string] {
  let mime = defaultMime
  let encoded = value
  if (value.startsWith('data:') && value.includes(';base64,')) {
    const index = value.indexOf(',')
    mime = value.slice(5, value.indexOf(';')).split(';')[0]
    encoded = value.slice(index + 1)
  }
  try {
    const binary = atob(encoded)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
    return [bytes, mime]
  } catch {
    throw new ModelCallError('模型返回的 Base64 数据无效')
  }
}

// ------------------------------------------------------------
// 连接测试
// ------------------------------------------------------------
export async function testModelConnection(
  config: ModelConfig,
  db?: SecretDb,
  ownerId?: string,
): Promise<string> {
  const hdrs = await buildHeaders(config, db, ownerId)

  if (isComfyUiVideo(config) && !config.extra_config?.test_path) {
    const url = videoUrl(config, 'video_submit_path', '/videos/generations', '/video_generation', '/contents/generations/tasks', '{workflow_id}')
    const options = pickOptions(config, 'video_options')
    const response = await fetch(url, {
      method: 'POST',
      headers: hdrs,
      body: JSON.stringify({ prompt: '', duration: 1, resolution: options.resolution ?? '480p竖' }),
    })
    const data = await parseJson(response)
    const code = String(data.code ?? '')
    const message = String(data.msg ?? '')
    if (code === 'RequestParameterIsWrong' && message.toLowerCase().includes('prompt')) {
      return '连接成功，ComfyUI Token 和工作流 ID 有效'
    }
    if (code && code.toLowerCase() !== 'success') {
      throw new ModelCallError(`视频工作流返回 ${code}: ${message || '未知错误'}`)
    }
    throw new ModelCallError('视频工作流未返回预期的参数校验结果')
  }

  if ((isMiniMaxVideo(config) || isArkVideo(config)) && !config.extra_config?.test_path) {
    const url = videoUrl(config, 'video_submit_path', '/videos/generations', '/video_generation', '/contents/generations/tasks', '{workflow_id}')
    const payload: Record<string, unknown> = { model: config.model_name }
    if (isArkVideo(config)) payload.content = [{ type: 'text', text: '' }]
    const response = await fetch(url, { method: 'POST', headers: hdrs, body: JSON.stringify(payload) })
    // 响应体只能读一次：先取出文本，后续判断与报错都复用它
    const rawText = await response.text().catch(() => '')
    const detail = rawText.toLowerCase()
    const markers = ['empty', 'required', 'missing', 'invalid', '不能为空', '必填']
    const inputError =
      ['prompt', 'content', 'text'].some((f) => detail.includes(f)) && markers.some((m) => detail.includes(m))
    if ([400, 406, 422].includes(response.status) && inputError) {
      return '连接成功，视频接口、认证和模型名称有效'
    }
    parseJsonText(response, rawText)
    throw new ModelCallError('视频接口未返回预期的参数校验结果')
  }

  const url = buildUrl(config, 'test_path', '/models')
  const response = await fetch(url, { headers: hdrs })
  const data = await parseJson(response)
  const availableModels = availableModelIds(data)
  const configured = config.model_name.trim()
  if (availableModels.size > 0) {
    const lowered = new Set([...availableModels].map((item) => item.toLowerCase()))
    if (!lowered.has(configured.toLowerCase())) {
      throw new ModelCallError(`认证成功，但模型名称“${configured}”不在服务商的可用模型列表中`)
    }
  }
  return '连接成功，认证信息和模型名称有效'
}

// ------------------------------------------------------------
// 文本生成
// ------------------------------------------------------------
export async function generateText(
  config: ModelConfig,
  systemPrompt: string,
  userPrompt: string,
  temperature = 0.7,
  db?: SecretDb,
): Promise<string> {
  if (config.model_type !== 'TEXT') throw new ModelCallError('所选配置不是文本模型')
  const payload: Record<string, unknown> = {
    model: config.model_name,
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userPrompt },
    ],
    temperature,
    ...pickOptions(config, 'text_options'),
  }
  const response = await fetch(buildUrl(config, 'text_path', '/chat/completions'), {
    method: 'POST',
    headers: await buildHeaders(config, db),
    body: JSON.stringify(payload),
  })
  const data = await parseJson(response)
  let content = nested(
    data,
    ['choices', 0, 'message', 'content'],
    ['choices', 0, 'text'],
    ['output_text'],
    ['data', 'output_text'],
  )
  if (Array.isArray(content)) {
    content = content
      .map((item) => (item && typeof item === 'object' ? String((item as Record<string, unknown>).text ?? '') : String(item)))
      .join('\n')
  }
  if (typeof content !== 'string' || !content.trim()) {
    throw new ModelCallError('文本模型返回内容为空或格式不受支持')
  }
  return content.trim()
}

// ------------------------------------------------------------
// 图片生成
// ------------------------------------------------------------
export async function generateImage(
  config: ModelConfig,
  prompt: string,
  size = '1024x1024',
  db?: SecretDb,
): Promise<[Uint8Array, string]> {
  if (config.model_type !== 'IMAGE') throw new ModelCallError('所选配置不是图片模型')
  const payload: Record<string, unknown> = {
    model: config.model_name,
    prompt,
    size,
    n: 1,
    response_format: 'b64_json',
    ...pickOptions(config, 'image_options'),
  }
  const response = await fetch(buildUrl(config, 'image_path', '/images/generations'), {
    method: 'POST',
    headers: await buildHeaders(config, db),
    body: JSON.stringify(payload),
  })
  const data = await parseJson(response)
  const encoded = nested(data, ['data', 0, 'b64_json'], ['b64_json'], ['image_base64'])
  if (typeof encoded === 'string' && encoded) return decodeBase64(encoded, 'image/png')
  const resultUrl = nested(data, ['data', 0, 'url'], ['url'], ['output', 0, 'url'], ['data', 'url'])
  if (typeof resultUrl === 'string' && resultUrl) return downloadMedia(resultUrl)
  throw new ModelCallError('图片模型返回格式不受支持，未找到图片数据或下载地址')
}

// ------------------------------------------------------------
// 视频提交（异步：只提交，返回 provider_task_id）
// ------------------------------------------------------------
export interface VideoSubmitInput {
  prompt: string
  duration: number
  imageDataUrls?: string[]
  requestOptions?: Record<string, unknown>
}

export async function submitVideo(
  config: ModelConfig,
  input: VideoSubmitInput,
  db?: SecretDb,
): Promise<{ providerTaskId?: string; data?: Uint8Array; mimeType?: string }> {
  if (config.model_type !== 'VIDEO') throw new ModelCallError('所选配置不是视频模型')
  const isMiniMax = isMiniMaxVideo(config)
  const isArk = isArkVideo(config)
  const isComfy = isComfyUiVideo(config)
  const duration = Number.isInteger(input.duration) ? input.duration : input.duration
  const videoOptions = { ...pickOptions(config, 'video_options'), ...(input.requestOptions ?? {}) }
  const referenceImages = (input.imageDataUrls ?? []).filter(Boolean)

  let payload: Record<string, unknown>
  if (isComfy) {
    payload = { prompt: input.prompt, duration, ...videoOptions }
    const configuredFields = config.extra_config?.reference_fields
    const referenceField = config.extra_config?.reference_field
    const template = String(config.extra_config?.reference_field_template ?? 'ref_image_{index}')
    referenceImages.forEach((image, index) => {
      let fieldName: string
      if (Array.isArray(configuredFields) && index < configuredFields.length) fieldName = String(configuredFields[index])
      else if (index === 0 && referenceField) fieldName = String(referenceField)
      else fieldName = template.replace('{index}', String(index))
      payload[fieldName] = image
    })
  } else if (isArk) {
    const flagNames: Record<string, string> = {
      resolution: 'rs', ratio: 'rt', fps: 'fps', seed: 'seed', camera_fixed: 'cf', watermark: 'wm',
    }
    const flags = [`--dur ${duration}`]
    for (const [option, flag] of Object.entries(flagNames)) {
      if (option in videoOptions) {
        let value = videoOptions[option]
        delete videoOptions[option]
        if (typeof value === 'boolean') value = String(value)
        flags.push(`--${flag} ${value}`)
      }
    }
    const content: Record<string, unknown>[] = [{ type: 'text', text: `${input.prompt} ${flags.join(' ')}` }]
    if (referenceImages.length > 0) content.push({ type: 'image_url', image_url: { url: referenceImages[0] } })
    payload = { model: config.model_name, content }
  } else {
    payload = { model: config.model_name, prompt: input.prompt, duration }
  }

  if (referenceImages.length > 0 && !isArk && !isComfy) {
    const defaultField = isMiniMax ? 'first_frame_image' : 'image'
    payload[String(config.extra_config?.reference_field ?? defaultField)] = referenceImages[0]
  }
  if (isMiniMax && duration === 10) payload.resolution = '768P'
  if (!isComfy) Object.assign(payload, videoOptions)

  const response = await fetch(
    videoUrl(config, 'video_submit_path', '/videos/generations', '/video_generation', '/contents/generations/tasks', '{workflow_id}'),
    { method: 'POST', headers: await buildHeaders(config, db), body: JSON.stringify(payload) },
  )

  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.startsWith('video/')) {
    return { data: new Uint8Array(await response.arrayBuffer()), mimeType: contentType.split(';')[0] }
  }

  const data = await parseJson(response)
  if (isComfy && String(data.code ?? '').toLowerCase() !== 'success') {
    throw new ModelCallError(`视频工作流提交失败：${data.msg ?? data.code ?? '未知错误'}`)
  }
  const directB64 = nested(data, ['b64_json'], ['data', 'b64_json'])
  if (typeof directB64 === 'string' && directB64) {
    const [bytes, mime] = decodeBase64(directB64, 'video/mp4')
    return { data: bytes, mimeType: mime }
  }
  const directUrl = nested(data, ['url'], ['video_url'], ['data', 'url'], ['data', 'video_url'], ['output', 'url'])
  if (typeof directUrl === 'string' && directUrl) {
    const [bytes, mime] = await downloadMedia(directUrl)
    return { data: bytes, mimeType: mime }
  }
  const providerTaskId = nested(data, ['id'], ['task_id'], ['data', 'id'], ['data', 'task_id'])
  if (providerTaskId == null) {
    const message = nested(data, ['error', 'message'], ['base_resp', 'status_msg'], ['message'])
    if (message) throw new ModelCallError(`视频生成请求失败：${message}`)
    throw new ModelCallError('视频模型返回格式不受支持，未找到任务 ID 或视频地址')
  }
  return { providerTaskId: String(providerTaskId) }
}

// ------------------------------------------------------------
// 视频轮询（单次：供 ai-video-poll 调用）
// ------------------------------------------------------------
export type PollOutcome =
  | { state: 'processing'; providerStatus: string }
  | { state: 'success'; data: Uint8Array; mimeType: string }
  | { state: 'failed'; message: string }

export async function pollVideoOnce(
  config: ModelConfig,
  providerTaskId: string,
  db?: SecretDb,
  ownerId?: string,
): Promise<PollOutcome> {
  const isComfy = isComfyUiVideo(config)
  const statusUrl = videoUrl(
    config,
    'video_status_path',
    '/videos/generations/{task_id}',
    '/query/video_generation?task_id={task_id}',
    '/contents/generations/tasks/{task_id}',
    'result/{task_id}',
  ).replace('{task_id}', providerTaskId)

  const response = await fetch(statusUrl, { headers: await buildHeaders(config, db, ownerId) })
  const pollData = await parseJson(response)
  if (isComfy && String(pollData.code ?? '').toLowerCase() !== 'success') {
    throw new ModelCallError(`视频工作流查询失败：${pollData.msg ?? pollData.code ?? '未知错误'}`)
  }

  const successStatuses = new Set(
    (config.extra_config?.success_statuses as string[] | undefined ?? ['succeeded', 'success', 'completed', 'done']).map((s) =>
      String(s).toLowerCase(),
    ),
  )
  const failureStatuses = new Set(
    (config.extra_config?.failure_statuses as string[] | undefined ?? ['fail', 'failed', 'error', 'expired', 'cancelled', 'canceled']).map(
      (s) => String(s).toLowerCase(),
    ),
  )

  const state = String(nested(pollData, ['status'], ['data', 'status']) ?? '').toLowerCase()
  const resultUrl = nested(
    pollData,
    ['url'], ['video_url'], ['data', 'url'], ['data', 'video_url'], ['output', 'url'],
    ['data', 'output', 'url'], ['content', 'video_url'], ['data', 'content', 'video_url'],
    ['results', 0, 'url'], ['data', 'results', 0, 'url'], ['results', 0], ['data', 'results', 0],
  )
  if (typeof resultUrl === 'string' && resultUrl && (!state || successStatuses.has(state))) {
    const [bytes, mime] = await downloadMedia(resultUrl)
    return { state: 'success', data: bytes, mimeType: mime }
  }

  const fileId = nested(pollData, ['file_id'], ['data', 'file_id'], ['file', 'id'])
  if (successStatuses.has(state) && fileId != null) {
    const fileUrl = videoUrl(
      config,
      'video_file_path',
      '/files/{file_id}',
      '/files/retrieve?file_id={file_id}',
      '/files/{file_id}',
      'files/{file_id}',
    ).replace('{file_id}', String(fileId))
    const fileResponse = await fetch(fileUrl, { headers: await buildHeaders(config, db, ownerId) })
    const fileData = await parseJson(fileResponse)
    const downloadUrl = nested(
      fileData,
      ['file', 'download_url'], ['download_url'], ['data', 'download_url'], ['data', 'file', 'download_url'],
    )
    if (typeof downloadUrl === 'string' && downloadUrl) {
      const [bytes, mime] = await downloadMedia(downloadUrl)
      return { state: 'success', data: bytes, mimeType: mime }
    }
    throw new ModelCallError('视频任务已完成，但未找到成片下载地址')
  }

  if (failureStatuses.has(state)) {
    const message = nested(pollData, ['error', 'message'], ['error'], ['message'], ['data', 'error'], ['base_resp', 'status_msg'])
    return { state: 'failed', message: `视频生成失败：${message ?? state}` }
  }

  return { state: 'processing', providerStatus: state.toUpperCase() || 'PROCESSING' }
}

/** 供 ai-video-poll 用的总超时判断。 */
export function pollTimeout(config: ModelConfig): number {
  return timeoutSeconds(config, 900)
}

export const MIME_EXTENSIONS: Record<string, string> = {
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'image/webp': '.webp',
  'video/mp4': '.mp4',
  'video/webm': '.webm',
  'video/quicktime': '.mov',
}
