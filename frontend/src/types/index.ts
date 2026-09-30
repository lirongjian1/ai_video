export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface User {
  id: string
  email: string
  username: string
  nickname: string
  role: 'ADMIN' | 'USER'
  status: 'ENABLED' | 'DISABLED'
  last_login_time: string | null
  created_at: string
  updated_at: string
}

export interface Project {
  id: number
  name: string
  description: string | null
  cover_file_id: number | null
  status: 'ACTIVE' | 'ARCHIVED' | 'DISABLED'
  created_by: string
  created_at: string
  updated_at: string
}

export interface AiFile {
  id: number
  project_id: number | null
  file_name: string
  original_name: string
  file_type: 'IMAGE' | 'VIDEO'
  mime_type: string
  file_size: number
  storage_bucket: string
  storage_path: string
  thumbnail_path: string | null
  width: number | null
  height: number | null
  duration: number | null
  source_type: 'UPLOAD' | 'AI_IMAGE' | 'AI_VIDEO' | 'VIDEO_MERGE'
  source_id: number | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface ModelConfig {
  id: number
  name: string
  model_type: 'TEXT' | 'IMAGE' | 'VIDEO'
  provider: string
  base_url: string | null
  model_name: string
  secret_ref: string | null
  extra_config: Record<string, unknown>
  status: 'ENABLED' | 'DISABLED'
  is_default: boolean
  created_by: string
  created_at: string
  updated_at: string
}

/** 密钥（仅掩码，明文永远不返回前端） */
export interface ApiSecret {
  id: number
  name: string
  provider: string
  description: string | null
  /** 形如 sk-1***abcd，仅用于列表展示 */
  masked: string
  /** 模型配置通过它引用本密钥 */
  secret_ref: string
  status: 'ENABLED' | 'DISABLED'
  created_at: string
  updated_at: string
}

export interface Prompt {
  id: number
  project_id: number | null
  name: string
  prompt_type: 'CHARACTER' | 'SCENE' | 'STORY_CONTENT' | 'SCRIPT' | 'STORYBOARD' | 'VIDEO' | 'CUSTOM'
  content: string
  negative_prompt: string | null
  variables: Record<string, unknown>
  status: 'ENABLED' | 'DISABLED'
  created_by: string
  created_at: string
  updated_at: string
}

export interface Character {
  id: number
  project_id: number
  name: string
  description: string | null
  appearance: string | null
  personality: string | null
  reference_file_id: number | null
  prompt_id: number | null
  status: 'ACTIVE' | 'DISABLED'
  created_by: string
  created_at: string
  updated_at: string
}

export interface Scene {
  id: number
  project_id: number
  name: string
  description: string | null
  environment: string | null
  atmosphere: string | null
  reference_file_id: number | null
  prompt_id: number | null
  status: 'ACTIVE' | 'DISABLED'
  created_by: string
  created_at: string
  updated_at: string
}

export interface Script {
  id: number
  project_id: number
  /** 本剧本依据的「内容故事」提示词；老剧本可能为空（不支持重新生成） */
  story_prompt_id: number | null
  title: string
  summary: string | null
  content: string
  duration: number | null
  status: 'DRAFT' | 'READY' | 'ARCHIVED'
  storyboard_count: number
  created_by: string
  created_at: string
  updated_at: string
}

/** 分镜段（storyboards）—— 每段固定 10 秒，内含 1~2 个镜头 */
export interface Storyboard {
  id: number
  script_id: number
  project_id: number
  sequence: number
  title: string
  description: string | null
  /** 本段剧情 */
  plot: string | null
  /** 本段主体动作 */
  subject_action: string | null
  duration: number | null
  camera: string | null
  dialogue: string | null
  video_prompt: string | null
  scene_id: number | null
  character_ids: number[]
  reference_file_ids: number[]
  status: 'DRAFT' | 'READY' | 'GENERATED'
  created_by: string
  created_at: string
  updated_at: string
}

/** 镜头（storyboard_shots）—— 段内时长均分 */
export interface StoryboardShot {
  id: number
  storyboard_id: number
  project_id: number | null
  sequence: number
  description: string | null
  duration: number | null
  created_by: string
  created_at: string
  updated_at: string
}

/** 分镜抽屉里的树形行：段与镜头统一成同一形状，用 __isShot 区分 */
export interface StoryboardTreeRow extends Storyboard {
  __key: string
  __isShot: boolean
  /** 镜头行专用：所属分镜段 id */
  __parentId?: number
  children?: StoryboardTreeRow[]
}

export interface AiTask {
  id: number
  project_id: number | null
  name: string
  task_type: 'TEXT' | 'IMAGE' | 'VIDEO' | 'MERGE'
  target_type: string | null
  target_id: number | null
  model_config_id: number | null
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'CANCELLED'
  progress: number
  provider_task_id: string | null
  provider_status: string | null
  request_payload: Record<string, unknown>
  result_payload: Record<string, unknown>
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  created_by: string
  created_at: string
  updated_at: string
}

