/**
 * ai-text —— 文本生成统一入口
 * 支持 action:
 *   connection-test  连接测试
 *   generate-prompt  生成角色三视图 / 场景提示词（含写库、任务记录）
 *   generate-script  生成六段分镜（含写库、任务记录）
 */
import { adminClient, fail, handler, json, readJson, requireUser } from '../_shared/supabase.ts'
import { generateText, testModelConnection, type ModelConfig } from '../_shared/gateway.ts'
import {
  CHARACTER_THREE_VIEW_PROMPT,
  SCENE_PROMPT,
  SCRIPT_SYSTEM_PROMPT,
  parseStoryboardJson,
} from '../_shared/prompts.ts'

interface Payload {
  action?: string
  model_config_id?: number
  project_id?: number | null
  name?: string
  keywords?: string
  generation_type?: string
  title?: string
  style?: string
}

async function loadConfig(db: ReturnType<typeof adminClient>, id: number): Promise<ModelConfig> {
  const { data, error } = await db.from('model_configs').select('*').eq('id', id).single()
  if (error || !data) throw new Error('模型配置不存在')
  if (data.status !== 'ENABLED') throw new Error('所选模型配置已停用')
  return data as ModelConfig
}

Deno.serve(
  handler(async (req) => {
    const user = await requireUser(req)
    if (!user) return fail('未登录', 401)

    const payload = await readJson<Payload>(req)
    const db = adminClient()

    // ---- 连接测试 ----
    if (payload.action === 'connection-test') {
      const config = await loadConfig(db, Number(payload.model_config_id))
      const message = await testModelConnection(config, db)
      return json({ ok: true, message })
    }

    if (!payload.model_config_id) return fail('缺少 model_config_id')

    // ---- 生成提示词 ----
    if (payload.action === 'generate-prompt') {
      const config = await loadConfig(db, payload.model_config_id)
      if (config.model_type !== 'TEXT') return fail('请选择文本模型')

      const isCharacter = payload.generation_type === 'CHARACTER_THREE_VIEW'
      const systemPrompt = isCharacter ? CHARACTER_THREE_VIEW_PROMPT : SCENE_PROMPT
      const promptType = isCharacter ? 'CHARACTER' : 'SCENE'
      const keywords = payload.keywords ?? ''

      const { data: task } = await db
        .from('tasks')
        .insert({
          project_id: payload.project_id ?? null,
          name: `生成提示词：${payload.name ?? ''}`,
          task_type: 'TEXT',
          model_config_id: config.id,
          status: 'RUNNING',
          progress: 20,
          request_payload: { generation_type: payload.generation_type, keywords },
          started_at: new Date().toISOString(),
          created_by: user.id,
        })
        .select()
        .single()

      try {
        const content = await generateText(config, systemPrompt, keywords, 0.7, db)
        const { data: record, error } = await db
          .from('prompts')
          .insert({
            project_id: payload.project_id ?? null,
            name: payload.name ?? '',
            prompt_type: promptType,
            content,
            variables: { keywords, generation_type: payload.generation_type, model_config_id: config.id },
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

    // ---- 生成六段分镜 ----
    if (payload.action === 'generate-script') {
      const config = await loadConfig(db, payload.model_config_id)
      if (config.model_type !== 'TEXT') return fail('请选择文本模型')
      if (!payload.project_id) return fail('缺少 project_id')

      const keywords = payload.keywords ?? ''
      const userPrompt = payload.style ? `${keywords}\n视觉风格：${payload.style}` : keywords

      const { data: task } = await db
        .from('tasks')
        .insert({
          project_id: payload.project_id,
          name: `生成六段分镜：${payload.title ?? ''}`,
          task_type: 'TEXT',
          model_config_id: config.id,
          status: 'RUNNING',
          progress: 15,
          request_payload: { keywords, style: payload.style ?? null },
          started_at: new Date().toISOString(),
          created_by: user.id,
        })
        .select()
        .single()

      try {
        const generated = parseStoryboardJson(
          await generateText(config, SCRIPT_SYSTEM_PROMPT, userPrompt, 0.6, db),
        )
        const { data: script, error } = await db
          .from('scripts')
          .insert({
            project_id: payload.project_id,
            title: payload.title ?? '',
            summary: String(generated.summary ?? keywords).slice(0, 5000),
            content: String(generated.content ?? keywords),
            duration: 60,
            status: 'READY',
            created_by: user.id,
          })
          .select()
          .single()
        if (error) throw new Error(error.message)

        const boards = generated.shots.map((shot, index) => {
          const i = index + 1
          if (!shot || typeof shot !== 'object') throw new Error(`第 ${i} 个分镜格式不正确`)
          return {
            script_id: script.id,
            project_id: payload.project_id,
            sequence: i,
            title: String(shot.title ?? `分镜 ${i}`).slice(0, 200),
            description: String(shot.description ?? ''),
            duration: 10,
            camera: String(shot.camera ?? '').slice(0, 200) || null,
            dialogue: String(shot.dialogue ?? '') || null,
            video_prompt: String(shot.video_prompt ?? shot.description ?? ''),
            character_ids: [],
            reference_file_ids: [],
            status: 'READY',
            created_by: user.id,
          }
        })
        const { data: insertedBoards, error: boardError } = await db
          .from('storyboards')
          .insert(boards)
          .select('id')
        if (boardError) throw new Error(boardError.message)

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
              },
              finished_at: new Date().toISOString(),
            })
            .eq('id', task.id)
        }
        return json({ ...script, storyboard_count: 6 }, 201)
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
