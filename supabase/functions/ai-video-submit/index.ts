/**
 * ai-video-submit —— 提交视频生成任务
 * 只做两件事：提交给厂商 + 记录 provider_task_id，立即返回。
 * 后续状态由 ai-video-poll 定时轮询处理（避免长轮询撞 Edge Function 时限）。
 */
import { adminClient, fail, handler, json, readJson, requireUser } from '../_shared/supabase.ts'
import { generateText, MIME_EXTENSIONS, submitVideo, type ModelConfig } from '../_shared/gateway.ts'
import {
  REFERENCE_INSTRUCTION,
  VIDEO_PROMPT_PREFIX,
  VIDEO_TRANSLATE_PROMPT,
  hasCjk,
  pickTranslationConfig,
} from '../_shared/prompts.ts'

interface Payload {
  storyboard_id?: number
  model_config_id?: number
  reference_file_ids?: number[]
  duration?: number
  resolution?: string
  seed?: number
}

Deno.serve(
  handler(async (req) => {
    const user = await requireUser(req)
    if (!user) return fail('未登录', 401)

    const payload = await readJson<Payload>(req)
    const db = adminClient()

    const { data: storyboard } = await db
      .from('storyboards')
      .select('*')
      .eq('id', payload.storyboard_id)
      .single()
    if (!storyboard) return fail('分镜不存在', 404)

    const { data: configRow } = await db
      .from('model_configs')
      .select('*')
      .eq('id', payload.model_config_id)
      .single()
    if (!configRow) return fail('模型配置不存在', 404)
    // service_role 绕过 RLS，需自行校验归属
    if (configRow.created_by !== user.id) return fail('模型配置不存在', 404)
    if (configRow.status !== 'ENABLED') return fail('所选模型配置已停用', 409)
    if (configRow.model_type !== 'VIDEO') return fail('请选择视频模型')
    const config = configRow as ModelConfig

    let prompt: string = storyboard.video_prompt || storyboard.description || ''
    if (!prompt) return fail('请先填写分镜的视频提示词或画面描述')

    const referenceIds = [...new Set(payload.reference_file_ids ?? [])]
    if (referenceIds.length > 9) return fail('参考图片最多选择 9 张')

    // 读取参考图并转 base64 data URL
    const imageDataUrls: string[] = []
    for (const fileId of referenceIds) {
      const { data: refFile } = await db.from('files').select('*').eq('id', fileId).single()
      if (!refFile || refFile.file_type !== 'IMAGE') return fail('参考文件必须是图片')
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(refFile.mime_type)) {
        return fail('参考图片仅支持 JPG、PNG 或 WebP 格式')
      }
      const { data: blob, error } = await db.storage.from('media').download(refFile.storage_path)
      if (error || !blob) return fail('参考图片读取失败')
      const buffer = new Uint8Array(await blob.arrayBuffer())
      let binary = ''
      for (let i = 0; i < buffer.length; i++) binary += String.fromCharCode(buffer[i])
      imageDataUrls.push(`data:${refFile.mime_type};base64,${btoa(binary)}`)
    }

    // 提示词整理：非中文则翻译；有参考图则注入一致性指令
    let translated = false
    if (!hasCjk(prompt)) {
      // 翻译模型只在本人的配置里挑选，避免读到别人的模型
      const { data: allConfigs } = await db
        .from('model_configs')
        .select('*')
        .eq('created_by', user.id)
      const translationConfig = pickTranslationConfig(config, (allConfigs ?? []) as ModelConfig[])
      if (!translationConfig) throw new Error('检测到英文提示词，但没有可用文本模型执行中文转换')
      prompt = (await generateText(translationConfig, VIDEO_TRANSLATE_PROMPT, prompt, 0.2, db)).trim()
      translated = true
    }
    // V2.0 生成的视频提示词已自带「固定前缀 + 固定结尾」，此处不再重复注入
    const hasReferenceInstruction =
      prompt.includes(VIDEO_PROMPT_PREFIX) || prompt.includes('严格参考所提供的')
    if (imageDataUrls.length > 0 && !hasReferenceInstruction) {
      prompt = `${REFERENCE_INSTRUCTION}\n${prompt}`
    }

    // 更新分镜参考图
    await db.from('storyboards').update({ reference_file_ids: referenceIds }).eq('id', storyboard.id)

    const { data: task } = await db
      .from('tasks')
      .insert({
        project_id: storyboard.project_id,
        name: `生成视频：${storyboard.title}`,
        task_type: 'VIDEO',
        target_type: 'STORYBOARD',
        target_id: storyboard.id,
        model_config_id: config.id,
        status: 'PENDING',
        progress: 10,
        request_payload: {
          reference_file_ids: referenceIds,
          duration: payload.duration ?? storyboard.duration ?? 10,
          resolution: payload.resolution ?? null,
          seed: payload.seed ?? null,
        },
        result_payload: {
          provider_prompt: prompt,
          prompt_translated: translated,
          reference_image_count: imageDataUrls.length,
        },
        created_by: user.id,
      })
      .select()
      .single()

    try {
      const requestOptions: Record<string, unknown> = {}
      if (payload.resolution != null) requestOptions.resolution = payload.resolution
      if (payload.seed != null) requestOptions.seed = payload.seed

      const result = await submitVideo(
        config,
        {
          prompt,
          duration: payload.duration ?? storyboard.duration ?? 10,
          imageDataUrls,
          requestOptions,
        },
        db,
      )

      // 厂商直接返回了成片
      if (result.data) {
        const mimeType = result.mimeType ?? 'video/mp4'
        const extension = MIME_EXTENSIONS[mimeType] ?? '.mp4'
        const date = new Date().toISOString().slice(0, 10).replace(/-/g, '')
        const storagePath = `generated/video/${date}/${storyboard.title}-${crypto.randomUUID().slice(0, 10)}${extension}`
        const { error: uploadError } = await db.storage
          .from('media')
          .upload(storagePath, result.data, { contentType: mimeType })
        if (uploadError) throw new Error(`上传失败：${uploadError.message}`)

        const fileName = storagePath.split('/').pop()!
        const { data: fileRecord } = await db
          .from('files')
          .insert({
            project_id: storyboard.project_id,
            file_name: fileName,
            original_name: fileName,
            file_type: 'VIDEO',
            mime_type: mimeType,
            file_size: result.data.byteLength,
            storage_bucket: 'media',
            storage_path: storagePath,
            duration: storyboard.duration ?? 10,
            source_type: 'AI_VIDEO',
            source_id: task!.id,
            created_by: user.id,
          })
          .select()
          .single()

        await db.from('storyboards').update({ status: 'GENERATED' }).eq('id', storyboard.id)
        await db
          .from('tasks')
          .update({
            status: 'SUCCESS',
            progress: 100,
            provider_status: 'SUCCESS',
            result_payload: {
              provider_prompt: prompt,
              prompt_translated: translated,
              reference_image_count: imageDataUrls.length,
              file_id: fileRecord!.id,
              storage_path: storagePath,
            },
            finished_at: new Date().toISOString(),
          })
          .eq('id', task!.id)
        return json({ ...task!, status: 'SUCCESS', progress: 100 }, 201)
      }

      // 异步任务：记录 provider_task_id，交给轮询
      await db
        .from('tasks')
        .update({
          status: 'RUNNING',
          progress: 20,
          provider_task_id: result.providerTaskId ?? null,
          provider_status: 'SUBMITTED',
          started_at: new Date().toISOString(),
        })
        .eq('id', task!.id)

      return json({ ...task!, status: 'RUNNING', provider_task_id: result.providerTaskId }, 201)
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
