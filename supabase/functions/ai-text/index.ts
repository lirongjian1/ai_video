/**
 * ai-text —— 文本生成统一入口
 * 支持 action:
 *   connection-test  连接测试
 *   generate-prompt  生成 角色三视图 / 场景概念图 / 内容故事（含写库、任务记录）
 *   generate-script  基于「内容故事」二次生成六段分镜（含写库、任务记录）
 *
 * V2.0：剧本改为「内容故事 → 二次生成」，落库为 段(storyboards) → 镜头(storyboard_shots) 两级结构。
 */
import { adminClient, fail, handler, json, readJson, requireUser } from '../_shared/supabase.ts'
import { generateText, testModelConnection, type ModelConfig } from '../_shared/gateway.ts'
import {
  CHARACTER_THREE_VIEW_PROMPT,
  SCENE_PROMPT,
  SCRIPT_FROM_STORY_SYSTEM_PROMPT,
  STORY_CONTENT_SYSTEM_PROMPT,
  buildVideoPrompt,
  normalizeAspectRatio,
  parseScriptFromStoryJson,
  parseStoryContentJson,
  withStructuredRetry,
  type AspectRatio,
} from '../_shared/prompts.ts'

/** 每个分镜段的固定时长（秒）。 */
const SEGMENT_DURATION = 10
/** 结构化输出最多尝试次数（V2.0 规定 3 次）。 */
const MAX_STRUCTURED_ATTEMPTS = 3

interface Payload {
  action?: string
  model_config_id?: number
  project_id?: number | null
  name?: string
  /** 生成提示词时的关键内容 */
  keywords?: string
  generation_type?: string
  /** 内容故事的画幅 */
  aspect_ratio?: string
  /** 二次生成剧本所依据的「内容故事」提示词 */
  story_prompt_id?: number
  title?: string
}

async function loadConfig(
  db: ReturnType<typeof adminClient>,
  id: number,
  ownerId: string,
): Promise<ModelConfig> {
  const { data, error } = await db.from('model_configs').select('*').eq('id', id).single()
  if (error || !data) throw new Error('模型配置不存在')
  // service_role 会绕过 RLS，这里必须自行校验归属
  if (data.created_by !== ownerId) throw new Error('模型配置不存在')
  if (data.status !== 'ENABLED') throw new Error('所选模型配置已停用')
  return data as ModelConfig
}

/** 把上一次的校验失败原因回喂给模型，要求它修正后重新输出完整 JSON。 */
function correctivePrompt(base: string, corrective: string | null): string {
  if (!corrective) return base
  return `${base}\n\n上一次输出不符合要求：${corrective}\n请修正后重新输出完整 JSON。`
}

Deno.serve(
  handler(async (req) => {
    const user = await requireUser(req)
    if (!user) return fail('未登录', 401)

    const payload = await readJson<Payload>(req)
    const db = adminClient()

    // ---- 连接测试 ----
    if (payload.action === 'connection-test') {
      const config = await loadConfig(db, Number(payload.model_config_id), user.id)
      const message = await testModelConnection(config, db, user.id)
      return json({ ok: true, message })
    }

    if (!payload.model_config_id) return fail('缺少 model_config_id')

    // ---- 生成提示词 ----
    if (payload.action === 'generate-prompt') {
      const config = await loadConfig(db, payload.model_config_id, user.id)
      if (config.model_type !== 'TEXT') return fail('请选择文本模型')

      const generationType = payload.generation_type ?? 'CHARACTER_THREE_VIEW'
      const isStoryContent = generationType === 'STORY_CONTENT'
      const isCharacter = generationType === 'CHARACTER_THREE_VIEW'
      const systemPrompt = isStoryContent
        ? STORY_CONTENT_SYSTEM_PROMPT
        : isCharacter
          ? CHARACTER_THREE_VIEW_PROMPT
          : SCENE_PROMPT
      const promptType = isStoryContent ? 'STORY_CONTENT' : isCharacter ? 'CHARACTER' : 'SCENE'
      const keywords = payload.keywords ?? ''
      const aspectRatio: AspectRatio = normalizeAspectRatio(payload.aspect_ratio, '16:9')
      // 内容故事需要把画幅明确告诉模型
      const userPrompt = isStoryContent ? `${keywords}\n\n画幅：${aspectRatio}` : keywords

      const { data: task } = await db
        .from('tasks')
        .insert({
          project_id: payload.project_id ?? null,
          name: `生成提示词：${payload.name ?? ''}`,
          task_type: 'TEXT',
          model_config_id: config.id,
          status: 'RUNNING',
          progress: 20,
          request_payload: {
            generation_type: generationType,
            keywords,
            aspect_ratio: isStoryContent ? aspectRatio : undefined,
          },
          started_at: new Date().toISOString(),
          created_by: user.id,
        })
        .select()
        .single()

      try {
        let content: string
        let variables: Record<string, unknown>

        if (isStoryContent) {
          const story = await withStructuredRetry(
            (raw) => parseStoryContentJson(raw, { aspectRatio }),
            (corrective) =>
              generateText(config, systemPrompt, correctivePrompt(userPrompt, corrective), 0.7, db),
            MAX_STRUCTURED_ATTEMPTS,
          )
          // content 存放「内容故事」JSON，作为剧本二次生成的唯一剧情依据
          content = JSON.stringify(story)
          variables = {
            keywords,
            generation_type: generationType,
            model_config_id: config.id,
            aspect_ratio: story.aspect_ratio,
            outline: story.outline,
            subject: story.subject,
            scene: story.scene,
            full_story: story.full_story,
            segment_count: story.segments.length,
          }
        } else {
          content = await generateText(config, systemPrompt, userPrompt, 0.7, db)
          variables = { keywords, generation_type: generationType, model_config_id: config.id }
        }

        const { data: record, error } = await db
          .from('prompts')
          .insert({
            project_id: payload.project_id ?? null,
            name: payload.name ?? '',
            prompt_type: promptType,
            content,
            variables,
            status: 'ENABLED',
            created_by: user.id,
          })
          .select()
          .single()
        if (error) throw new Error(error.message)

        if (task) {
          await db
            .from('tasks')
            .update({
              status: 'SUCCESS',
              progress: 100,
              target_type: 'PROMPT',
              target_id: record.id,
              result_payload: { prompt_id: record.id },
              finished_at: new Date().toISOString(),
            })
            .eq('id', task.id)
        }
        return json(record, 201)
      } catch (error) {
        if (task) {
          await db
            .from('tasks')
            .update({
              status: 'FAILED',
              progress: 100,
              error_message: error instanceof Error ? error.message : String(error),
              finished_at: new Date().toISOString(),
            })
            .eq('id', task.id)
        }
        throw error
      }
    }

    // ---- 基于「内容故事」二次生成六段分镜 ----
    if (payload.action === 'generate-script') {
      const config = await loadConfig(db, payload.model_config_id, user.id)
      if (config.model_type !== 'TEXT') return fail('请选择文本模型')
      if (!payload.project_id) return fail('缺少 project_id')
      if (!payload.story_prompt_id) return fail('请选择内容故事')

      // 内容故事是唯一剧情依据，必须存在、属于本人、类型正确且未停用
      const { data: storyPrompt, error: storyError } = await db
        .from('prompts')
        .select('*')
        .eq('id', payload.story_prompt_id)
        .single()
      if (storyError || !storyPrompt) return fail('内容故事不存在', 404)
      if (storyPrompt.created_by !== user.id) return fail('内容故事不存在', 404)
      if (storyPrompt.prompt_type !== 'STORY_CONTENT') return fail('所选提示词不是「内容故事」类型')
      if (storyPrompt.status !== 'ENABLED') return fail('所选内容故事已停用')

      const storyContent = String(storyPrompt.content ?? '').trim()
      if (!storyContent) return fail('所选内容故事内容为空')

      const userPrompt = `内容故事（JSON）：\n${storyContent}`

      const { data: task } = await db
        .from('tasks')
        .insert({
          project_id: payload.project_id,
          name: `生成六段分镜：${payload.title ?? ''}`,
          task_type: 'TEXT',
          model_config_id: config.id,
          status: 'RUNNING',
          progress: 15,
          request_payload: { story_prompt_id: payload.story_prompt_id },
          started_at: new Date().toISOString(),
          created_by: user.id,
        })
        .select()
        .single()

      try {
        const generated = await withStructuredRetry(
          parseScriptFromStoryJson,
          (corrective) =>
            generateText(
              config,
              SCRIPT_FROM_STORY_SYSTEM_PROMPT,
              correctivePrompt(userPrompt, corrective),
              0.6,
              db,
            ),
          MAX_STRUCTURED_ATTEMPTS,
        )

        const { data: script, error } = await db
          .from('scripts')
          .insert({
            project_id: payload.project_id,
            story_prompt_id: storyPrompt.id,
            title: payload.title ?? '',
            summary: String(generated.summary ?? storyPrompt.name ?? '').slice(0, 5000),
            content: generated.content,
            duration: SEGMENT_DURATION * generated.segments.length,
            status: 'READY',
            created_by: user.id,
          })
          .select()
          .single()
        if (error) throw new Error(error.message)

        // 段：固定 6 条，每条 10 秒
        const boardRows = generated.segments.map((segment, index) => {
          const i = index + 1
          const title = segment.plot || segment.description || `分镜段 ${i}`
          return {
            script_id: script.id,
            project_id: payload.project_id,
            sequence: i,
            title: title.slice(0, 200),
            description: segment.description,
            plot: segment.plot || null,
            subject_action: segment.subject_action || null,
            duration: SEGMENT_DURATION,
            camera: segment.camera.slice(0, 200) || null,
            dialogue: segment.dialogue || null,
            // 固定前缀 + 固定结尾，且保证 ≤150 字符
            video_prompt: buildVideoPrompt(segment.video_prompt),
            character_ids: [],
            reference_file_ids: [],
            status: 'READY',
            created_by: user.id,
          }
        })
        const { data: insertedBoards, error: boardError } = await db
          .from('storyboards')
          .insert(boardRows)
          .select('id, sequence')
        if (boardError) throw new Error(boardError.message)

        // 镜头：每段 1~2 条，段内时长均分
        const boardIdBySequence = new Map<number, number>(
          (insertedBoards ?? []).map((row) => [Number(row.sequence), Number(row.id)]),
        )
        const shotRows = generated.segments.flatMap((segment) => {
          const storyboardId = boardIdBySequence.get(segment.sequence)
          if (!storyboardId) return []
          const shotDuration = Number((SEGMENT_DURATION / segment.shots.length).toFixed(2))
          return segment.shots.map((shot, index) => ({
            storyboard_id: storyboardId,
            project_id: payload.project_id,
            sequence: index + 1,
            description: shot.description,
            duration: shotDuration,
            created_by: user.id,
          }))
        })
        if (shotRows.length) {
          const { error: shotError } = await db.from('storyboard_shots').insert(shotRows)
          if (shotError) throw new Error(shotError.message)
        }

        if (task) {
          await db
            .from('tasks')
            .update({
              status: 'SUCCESS',
              progress: 100,
              target_type: 'SCRIPT',
              target_id: script.id,
              result_payload: {
                script_id: script.id,
                storyboard_ids: (insertedBoards ?? []).map((b) => b.id),
                shot_count: shotRows.length,
              },
              finished_at: new Date().toISOString(),
            })
            .eq('id', task.id)
        }
        return json(
          { ...script, storyboard_count: boardRows.length, shot_count: shotRows.length },
          201,
        )
      } catch (error) {
        if (task) {
          await db
            .from('tasks')
            .update({
              status: 'FAILED',
              progress: 100,
              error_message: error instanceof Error ? error.message : String(error),
              finished_at: new Date().toISOString(),
            })
            .eq('id', task.id)
        }
        throw error
      }
    }

    return fail('未知的 action')
  }),
)
