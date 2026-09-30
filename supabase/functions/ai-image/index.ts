/**
 * ai-image —— 图片生成
 * 流程：读提示词 → (中文自动翻译英文) → 调图片模型 → 上传 Storage → 写 files 表 → 更新任务
 */
import { adminClient, fail, handler, json, readJson, requireUser } from '../_shared/supabase.ts'
import { generateImage, generateText, MIME_EXTENSIONS, type ModelConfig } from '../_shared/gateway.ts'
import { IMAGE_TRANSLATE_PROMPT, hasCjk, pickTranslationConfig } from '../_shared/prompts.ts'

interface Payload {
  prompt_id?: number
  model_config_id?: number
  project_id?: number | null
  name?: string
  size?: string
}

Deno.serve(
  handler(async (req) => {
    const user = await requireUser(req)
    if (!user) return fail('未登录', 401)

    const payload = await readJson<Payload>(req)
    const db = adminClient()

    const { data: prompt } = await db.from('prompts').select('*').eq('id', payload.prompt_id).single()
    if (!prompt) return fail('提示词不存在', 404)

    const { data: configRow } = await db
      .from('model_configs')
      .select('*')
      .eq('id', payload.model_config_id)
      .single()
    if (!configRow) return fail('模型配置不存在', 404)
    if (configRow.status !== 'ENABLED') return fail('所选模型配置已停用', 409)
    if (configRow.model_type !== 'IMAGE') return fail('请选择图片模型')
    const config = configRow as ModelConfig

    const projectId = payload.project_id ?? prompt.project_id ?? null

    const { data: task } = await db
      .from('tasks')
      .insert({
        project_id: projectId,
        name: `生成图片：${payload.name ?? ''}`,
        task_type: 'IMAGE',
        target_type: 'PROMPT',
        target_id: prompt.id,
        model_config_id: config.id,
        status: 'PENDING',
        request_payload: { prompt_id: prompt.id, name: payload.name ?? null, size: payload.size ?? '1024x1024' },
        created_by: user.id,
      })
      .select()
      .single()

    try {
      await db
        .from('tasks')
        .update({ status: 'RUNNING', progress: 10, started_at: new Date().toISOString() })
        .eq('id', task!.id)

      let content: string = prompt.content
      if (prompt.negative_prompt) content = `${content}\nNegative prompt: ${prompt.negative_prompt}`

      let translated = false
      if (hasCjk(content)) {
        const { data: allConfigs } = await db.from('model_configs').select('*')
        const translationConfig = pickTranslationConfig(config, (allConfigs ?? []) as ModelConfig[])
        if (!translationConfig) throw new Error('检测到中文提示词，但没有可用文本模型执行英文转换')
        content = (
          await generateText(translationConfig, IMAGE_TRANSLATE_PROMPT, content, 0.2, db)
        ).trim()
        translated = true
      }

      await db
        .from('tasks')
        .update({
          progress: 25,
          result_payload: { provider_prompt: content, prompt_translated: translated },
        })
        .eq('id', task!.id)

      const [bytes, mimeType] = await generateImage(
        config,
        content,
        String(payload.size ?? '1024x1024'),
        db,
      )

      const extension = MIME_EXTENSIONS[mimeType] ?? '.png'
      const safeName = (payload.name ?? 'image').replace(/\.[^.]+$/, '').trim() || 'image'
      const date = new Date().toISOString().slice(0, 10).replace(/-/g, '')
      const storagePath = `generated/image/${date}/${safeName}-${crypto.randomUUID().slice(0, 10)}${extension}`

      const { error: uploadError } = await db.storage
        .from('media')
        .upload(storagePath, bytes, { contentType: mimeType, upsert: false })
      if (uploadError) throw new Error(`上传失败：${uploadError.message}`)

      const fileName = storagePath.split('/').pop()!
      const { data: fileRecord, error: fileError } = await db
        .from('files')
        .insert({
          project_id: projectId,
          file_name: fileName,
          original_name: fileName,
          file_type: 'IMAGE',
          mime_type: mimeType,
          file_size: bytes.byteLength,
          storage_bucket: 'media',
          storage_path: storagePath,
          source_type: 'AI_IMAGE',
          source_id: task!.id,
          created_by: user.id,
        })
        .select()
        .single()
      if (fileError) throw new Error(fileError.message)

      await db
        .from('tasks')
        .update({
          status: 'SUCCESS',
          progress: 100,
          result_payload: {
            provider_prompt: content,
            prompt_translated: translated,
            file_id: fileRecord.id,
            storage_path: storagePath,
          },
          finished_at: new Date().toISOString(),
        })
        .eq('id', task!.id)

      return json({ ...fileRecord, task_id: task!.id }, 201)
    } catch (error) {
      await db
        .from('tasks')
        .update({
          status: 'FAILED',
          progress: 100,
          error_message: error instanceof Error ? error.message : String(error),
          finished_at: new Date().toISOString(),
        })
        .eq('id', task!.id)
      throw error
    }
  }),
)
