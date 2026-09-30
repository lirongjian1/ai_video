/**
 * 提示词模板 —— 与后端 workflow.py 中的 system prompt 完全一致。
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

export const SCRIPT_SYSTEM_PROMPT =
  '你是一名短视频导演和分镜师。请把用户描述改编为连续的 60 秒故事，严格拆分为 ' +
  '6 个分镜，每个分镜 10 秒。所有自然语言字段必须使用简体中文，不得输出英文提示词。' +
  '仅输出严格 JSON，不要使用 Markdown。JSON 结构必须为：' +
  '{"summary":"故事摘要","content":"完整故事梗概","shots":[' +
  '{"sequence":1,"title":"镜头标题","description":"画面描述","camera":"景别和运镜",' +
  '"dialogue":"台词或旁白","video_prompt":"可直接交给视频模型的完整提示词"}]}. ' +
  'shots 数组必须正好包含 6 项，sequence 从 1 到 6。人物或动物主体的外貌、体型、' +
  '毛色、发型、服装、配饰以及场景布局必须在全部分镜中保持一致。每个 video_prompt ' +
  '必须是完整中文句子，并以‘严格参考所提供的人物、动物主体和场景参考图，保持主体' +
  '身份、外貌、造型与场景一致’开头，再描述主体动作、环境、景别、运镜、光线和视觉' +
  '风格；不要写 8K、超高清等与工作流分辨率参数冲突的词。'

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

/** 解析分镜 JSON，容错剥离 Markdown 代码块。 */
export function parseStoryboardJson(content: string): {
  summary?: string
  content?: string
  shots: Record<string, unknown>[]
} {
  let cleaned = content.trim()
  if (cleaned.startsWith('```')) {
    cleaned = cleaned.split('\n').slice(1).join('\n')
    if (cleaned.endsWith('```')) cleaned = cleaned.slice(0, -3)
  }
  const start = cleaned.indexOf('{')
  const end = cleaned.lastIndexOf('}')
  if (start < 0 || end <= start) throw new Error('文本模型未返回有效的分镜 JSON')
  const value = JSON.parse(cleaned.slice(start, end + 1))
  if (!value || typeof value !== 'object') throw new Error('分镜结果必须是 JSON 对象')
  const shots = (value as Record<string, unknown>).shots
  if (!Array.isArray(shots) || shots.length !== 6) throw new Error('文本模型必须返回正好 6 个分镜')
  return value as { summary?: string; content?: string; shots: Record<string, unknown>[] }
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
