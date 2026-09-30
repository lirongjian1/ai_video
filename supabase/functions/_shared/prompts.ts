/**
 * 提示词模板 —— 与后端 workflow.py 中的 system prompt 保持一致。
 *
 * V2.0 新增：
 *   - 内容故事（STORY_CONTENT）系统提示词与结构化解析
 *   - 剧本二次生成系统提示词与结构化解析（段 → 镜头两级）
 *   - 视频提示词固定前后缀拼装（≤150 字符）
 *   - 结构化输出失败重试包装器
 */
import type { ModelConfig } from './gateway.ts'

export const CHARACTER_THREE_VIEW_PROMPT =
  'You are a professional visual development artist. First identify whether the ' +
  "user's subject is a human, a real animal, a fantasy creature, or an object, then " +
  'create one concise production-ready three-view model-sheet prompt. Always show ' +
  'the same subject in consistent front, side, and rear orthographic views, with a ' +
  'neutral pose, consistent proportions, a clean background, no text, and no ' +
  'watermark. For a human or humanoid subject, make the character clearly adult ' +
  'aged 21 or older and preserve only clothing and accessories requested by the ' +
  'user. For a real animal, preserve natural anatomy, posture, fur, scales, feathers, ' +
  'markings, and species traits; do not add clothing, accessories, human anatomy, ' +
  'or anthropomorphic behavior unless the user explicitly requests them. For a ' +
  'fantasy creature or object, preserve its native structure and do not invent human ' +
  'traits. Never introduce major elements that were not requested. Add appropriate ' +
  'materials, colors, lighting, and image-quality details. Use positive, ' +
  'family-friendly wording. Write the final prompt in Simplified Chinese and output ' +
  'only that prompt.'

export const SCENE_PROMPT =
  'You are a professional film environment concept designer. Create one concise, ' +
  "production-ready image prompt from the user's description. Include spatial " +
  'layout, time of day, weather, lighting, color palette, camera angle, environment ' +
  'details, atmosphere, and image quality. Do not include people, text, or ' +
  'watermarks. Write the final prompt in Simplified Chinese and output only that ' +
  'prompt.'

// ------------------------------------------------------------
// V2.0 · 内容故事（STORY_CONTENT）
// ------------------------------------------------------------
export type AspectRatio = '16:9' | '9:16'

export const STORY_CONTENT_SYSTEM_PROMPT =
  '你是一名短剧编剧。请根据用户给出的关键内容，写出一个完整可拍的故事，并严格输出 JSON。\n' +
  '硬性要求：\n' +
  '1. 只输出严格 JSON，禁止 Markdown 代码块，禁止任何解释文字。\n' +
  '2. JSON 结构必须为：' +
  '{"outline":"故事大纲","subject":"主体","scene":"场景","aspect_ratio":"16:9",' +
  '"full_story":"完整故事","segments":[{"sequence":1,"plot":"本段剧情",' +
  '"subject_action":"本段主体动作","description":"本段画面描述",' +
  '"shots":[{"description":"镜头画面描述"}]}]}。\n' +
  '3. segments 必须正好 6 段，sequence 从 1 到 6，整体构成 60 秒故事。\n' +
  '4. 每一段的 shots 数组必须包含 1 个或 2 个镜头，不能为空，也不能超过 2 个。\n' +
  '5. aspect_ratio 必须原样回填用户指定的画幅（16:9 或 9:16）。\n' +
  '6. subject 要写清主体的外貌、体型、发型、服装与配饰；scene 要写清地点、时间与氛围；' +
  'full_story 要有完整的起承转合。\n' +
  '7. 全篇使用简体中文，不要出现英文提示词，不要写 8K、超高清等与工作流分辨率冲突的词。'

// ------------------------------------------------------------
// V2.0 · 剧本二次生成（内容故事 → 六段分镜）
// ------------------------------------------------------------
export const SCRIPT_FROM_STORY_SYSTEM_PROMPT =
  '你是一名短视频导演和分镜师。用户会给出一份「内容故事」JSON，你必须严格基于它改编出 60 秒分镜，' +
  '不得改变主体、场景、冲突、事件顺序与结局。\n' +
  '硬性要求：\n' +
  '1. 只输出严格 JSON，禁止 Markdown 代码块，禁止任何解释文字。\n' +
  '2. JSON 结构必须为：' +
  '{"summary":"故事摘要","content":"完整故事","segments":[{"sequence":1,"plot":"本段剧情",' +
  '"subject_action":"本段主体动作","description":"本段画面描述","camera":"景别和运镜",' +
  '"dialogue":"台词或旁白","video_prompt":"视频提示词主体",' +
  '"shots":[{"description":"镜头画面描述"}]}]}。\n' +
  '3. segments 必须正好 6 段，sequence 从 1 到 6，每段固定 10 秒。\n' +
  '4. 每一段的 shots 数组必须包含 1 个或 2 个镜头；段内所有镜头均分这 10 秒。\n' +
  '5. video_prompt 只写「主体动作 + 环境 + 景别运镜 + 光线风格」，不要写前后缀，' +
  '长度不超过 110 个字符，不要写 8K、超高清等与工作流分辨率冲突的词。\n' +
  '6. 主体外貌、体型、毛色、发型、服装、配饰以及场景布局必须在全部分镜中保持一致。\n' +
  '7. 全篇使用简体中文。'

// ------------------------------------------------------------
// 视频提示词：固定前缀 + 固定结尾（合计 ≤150 字符）
// ------------------------------------------------------------
export const VIDEO_PROMPT_PREFIX = '严格使用我提供的主体参考图和场景参考图，'
export const VIDEO_PROMPT_SUFFIX = '，不要字幕、文字、Logo或水印。'
export const VIDEO_PROMPT_MAX_LENGTH = 150

/** 扣除固定前后缀后，正文可用的字符数。 */
export const VIDEO_PROMPT_BODY_BUDGET =
  VIDEO_PROMPT_MAX_LENGTH - VIDEO_PROMPT_PREFIX.length - VIDEO_PROMPT_SUFFIX.length

const VIDEO_PROMPT_FALLBACK_BODY = '保持主体与场景一致，自然连贯地推进动作'

/**
 * 按 V2.0 规范拼装视频提示词：固定前缀 + 正文 + 固定结尾，且总长不超过 150 字符。
 * 超出部分从正文尾部截断，不会破坏前后缀。
 */
export function buildVideoPrompt(body: string): string {
  const cleaned = String(body ?? '')
    .replace(/\s+/g, ' ')
    .replace(/^[，,、。：:\s]+/, '')
    .replace(/[。\s]+$/, '')
    .trim()
  const text = cleaned || VIDEO_PROMPT_FALLBACK_BODY
  const trimmed = text.length > VIDEO_PROMPT_BODY_BUDGET ? text.slice(0, VIDEO_PROMPT_BODY_BUDGET) : text
  return `${VIDEO_PROMPT_PREFIX}${trimmed}${VIDEO_PROMPT_SUFFIX}`
}

export const IMAGE_TRANSLATE_PROMPT =
  "Translate the user's visual design description into one concise English image " +
  'generation prompt. Preserve subject, appearance, clothing, composition, camera, ' +
  'lighting, materials, colors, and style. Treat every human subject as an adult ' +
  'aged 21 or older and keep all clothing details intact. Use positive, neutral, ' +
  'family-friendly wording. Do not include explanations, safety terminology, or ' +
  'negative concepts. Output only the English image prompt.'

export const VIDEO_TRANSLATE_PROMPT =
  '请把用户的视频生成提示词准确翻译并整理为简体中文，保留主体、动作、' +
  '场景、景别、运镜、光线和视觉风格。不要解释，不要补充英文，只输出一段' +
  '可以直接提交给视频模型的中文提示词。'

export const REFERENCE_INSTRUCTION =
  '严格参考所提供的人物、动物主体和场景参考图，保持主体身份、外貌、体型、' +
  '毛色、发型、服装、配饰，以及场景布局、色彩和光线一致；不得擅自替换主体、' +
  '改变造型或重构场景。'

const CJK_PATTERN = /[\u3400-\u9fff]/

export function hasCjk(text: string): boolean {
  return CJK_PATTERN.test(text)
}

// ------------------------------------------------------------
// JSON 解析工具
// ------------------------------------------------------------

/** 剥离 Markdown 代码块并截取最外层 JSON 对象。 */
function extractJsonObject(content: string): Record<string, unknown> {
  let cleaned = String(content ?? '').trim()
  if (cleaned.startsWith('```')) {
    cleaned = cleaned.split('\n').slice(1).join('\n')
    if (cleaned.trimEnd().endsWith('```')) cleaned = cleaned.trimEnd().slice(0, -3)
  }
  const start = cleaned.indexOf('{')
  const end = cleaned.lastIndexOf('}')
  if (start < 0 || end <= start) throw new Error('文本模型未返回有效的 JSON')
  let value: unknown
  try {
    value = JSON.parse(cleaned.slice(start, end + 1))
  } catch {
    throw new Error('文本模型返回的内容不是合法 JSON')
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('JSON 结果必须是一个对象')
  }
  return value as Record<string, unknown>
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : value == null ? '' : String(value).trim()
}

function fieldOf(source: unknown, key: string): unknown {
  return source && typeof source === 'object' ? (source as Record<string, unknown>)[key] : undefined
}

/** 把任意输入规整为 16:9 / 9:16。 */
export function normalizeAspectRatio(value: unknown, fallback: AspectRatio = '16:9'): AspectRatio {
  const text = asText(value)
  if (text === '9:16') return '9:16'
  if (text === '16:9') return '16:9'
  return fallback
}

// ------------------------------------------------------------
// 内容故事结构化结果
// ------------------------------------------------------------
export interface StoryContentShot {
  description: string
}

export interface StoryContentSegment {
  sequence: number
  plot: string
  subject_action: string
  description: string
  shots: StoryContentShot[]
}

export interface StoryContent {
  outline: string
  subject: string
  scene: string
  aspect_ratio: AspectRatio
  full_story: string
  segments: StoryContentSegment[]
}

function parseShots(raw: unknown, label: string): StoryContentShot[] {
  if (!Array.isArray(raw)) throw new Error(`${label}的 shots 必须是数组`)
  if (raw.length < 1 || raw.length > 2) {
    throw new Error(`${label}必须包含 1~2 个镜头，当前 ${raw.length} 个`)
  }
  return raw.map((shot, index) => {
    const j = index + 1
    if (!shot || typeof shot !== 'object') throw new Error(`${label}第 ${j} 个镜头格式不正确`)
    const description = asText(fieldOf(shot, 'description'))
    if (!description) throw new Error(`${label}第 ${j} 个镜头缺少 description`)
    return { description }
  })
}

/** 解析「内容故事」JSON，校验 6 段、每段 1~2 个镜头。 */
export function parseStoryContentJson(
  content: string,
  options: { aspectRatio?: AspectRatio } = {},
): StoryContent {
  const value = extractJsonObject(content)
  const rawSegments = value.segments
  if (!Array.isArray(rawSegments)) throw new Error('segments 必须是数组')
  if (rawSegments.length !== 6) {
    throw new Error(`segments 必须正好 6 段，当前 ${rawSegments.length} 段`)
  }
  const segments = rawSegments.map((item, index) => {
    const i = index + 1
    if (!item || typeof item !== 'object') throw new Error(`第 ${i} 段格式不正确`)
    return {
      sequence: i,
      plot: asText(fieldOf(item, 'plot')),
      subject_action: asText(fieldOf(item, 'subject_action')),
      description: asText(fieldOf(item, 'description')),
      shots: parseShots(fieldOf(item, 'shots'), `第 ${i} 段`),
    }
  })
  const subject = asText(value.subject)
  const scene = asText(value.scene)
  const fullStory = asText(value.full_story)
  if (!subject) throw new Error('缺少 subject（主体描述）')
  if (!scene) throw new Error('缺少 scene（场景描述）')
  if (!fullStory) throw new Error('缺少 full_story（完整故事）')
  return {
    outline: asText(value.outline),
    subject,
    scene,
    aspect_ratio: normalizeAspectRatio(value.aspect_ratio, options.aspectRatio ?? '16:9'),
    full_story: fullStory,
    segments,
  }
}

// ------------------------------------------------------------
// 剧本（二次生成）结构化结果
// ------------------------------------------------------------
export interface ScriptSegment {
  sequence: number
  plot: string
  subject_action: string
  description: string
  camera: string
  dialogue: string
  video_prompt: string
  shots: StoryContentShot[]
}

export interface ScriptFromStory {
  summary: string
  content: string
  segments: ScriptSegment[]
}

/** 解析剧本二次生成结果，校验 6 段、每段 1~2 个镜头。 */
export function parseScriptFromStoryJson(content: string): ScriptFromStory {
  const value = extractJsonObject(content)
  const rawSegments = value.segments
  if (!Array.isArray(rawSegments)) throw new Error('segments 必须是数组')
  if (rawSegments.length !== 6) {
    throw new Error(`segments 必须正好 6 段，当前 ${rawSegments.length} 段`)
  }
  const segments = rawSegments.map((item, index) => {
    const i = index + 1
    if (!item || typeof item !== 'object') throw new Error(`第 ${i} 段格式不正确`)
    const description = asText(fieldOf(item, 'description'))
    const videoPrompt = asText(fieldOf(item, 'video_prompt'))
    if (!videoPrompt) throw new Error(`第 ${i} 段缺少 video_prompt`)
    return {
      sequence: i,
      plot: asText(fieldOf(item, 'plot')),
      subject_action: asText(fieldOf(item, 'subject_action')),
      description,
      camera: asText(fieldOf(item, 'camera')),
      dialogue: asText(fieldOf(item, 'dialogue')),
      video_prompt: videoPrompt,
      shots: parseShots(fieldOf(item, 'shots'), `第 ${i} 段`),
    }
  })
  const summary = asText(value.summary)
  const story = asText(value.content)
  if (!story) throw new Error('缺少 content（完整故事）')
  return { summary, content: story, segments }
}

// ------------------------------------------------------------
// 结构化输出重试
// ------------------------------------------------------------

/**
 * 结构化生成的重试包装器：解析失败时把「校验原因」回喂给模型再试，
 * 最多尝试 maxAttempts 次（V2.0 规定 3 次）。
 *
 * @param parse      解析 + 校验函数，失败时抛出带原因的 Error
 * @param generate   真正的生成函数，参数为「上一次的校验失败原因」（首次为 null）
 */
export async function withStructuredRetry<T>(
  parse: (content: string) => T,
  generate: (corrective: string | null) => Promise<string>,
  maxAttempts = 3,
): Promise<T> {
  let lastReason = ''
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const content = await generate(attempt === 1 ? null : lastReason)
    try {
      return parse(content)
    } catch (error) {
      lastReason = error instanceof Error ? error.message : String(error)
    }
  }
  throw new Error(`结构化输出连续 ${maxAttempts} 次未通过校验：${lastReason}`)
}

/** 取翻译模型：优先 extra_config 指定，否则取默认 TEXT 模型。 */
export function pickTranslationConfig(
  mediaConfig: ModelConfig,
  allConfigs: ModelConfig[],
): ModelConfig | null {
  const configuredId = mediaConfig.extra_config?.translation_model_config_id
  if (configuredId) {
    const found = allConfigs.find((item) => item.id === Number(configuredId))
    if (found && found.model_type === 'TEXT' && found.status === 'ENABLED') return found
    throw new Error('模型配置的翻译模型不可用')
  }
  const candidates = allConfigs
    .filter((item) => item.model_type === 'TEXT' && item.status === 'ENABLED')
    .sort((a, b) => Number(b.is_default) - Number(a.is_default))
  return candidates[0] ?? null
}
