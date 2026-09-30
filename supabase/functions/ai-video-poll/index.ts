/**
 * ai-video-poll —— 视频任务轮询
 * 由 pg_cron / 定时任务触发（也允许带密钥手动触发）。
 * 每次只轮询一批「已提交但未完成」的任务，单次执行，不阻塞。
 */
import { adminClient, fail, handler, json } from '../_shared/supabase.ts'
import { pollVideoOnce, pollTimeout, MIME_EXTENSIONS, type ModelConfig } from '../_shared/gateway.ts'

const BATCH_SIZE = 10

Deno.serve(
  handler(async (req) => {
    // 定时触发需带共享密钥，避免被外部随意调用
    const cronSecret = Deno.env.get('CRON_SECRET')
    const provided = req.headers.get('x-cron-secret')
    if (cronSecret && provided !== cronSecret) {
      return fail('未授权', 401)
    }

    const db = adminClient()
    const { data: tasks } = await db
      .from('tasks')
      .select('*')
      .eq('task_type', 'VIDEO')
      .eq('status', 'RUNNING')
      .not('provider_task_id', 'is', null)
      .limit(BATCH_SIZE)

    const results: Record<string, unknown>[] = []

    for (const task of tasks ?? []) {
      try {
        // 只取任务归属者自己的模型配置，避免跨用户解析密钥
        const { data: configRow } = await db
          .from('model_configs')
          .select('*')
          .eq('id', task.model_config_id)
          .eq('created_by', task.created_by)
          .single()
        if (!configRow) {
          await db
            .from('tasks')
            .update({ status: 'FAILED', error_message: '视频模型配置不存在', finished_at: new Date().toISOString() })
            .eq('id', task.id)
          continue
        }
        const config = configRow as ModelConfig

        // 超时保护
        const timeout = pollTimeout(config)
        const startedAt = task.started_at ? new Date(task.started_at).getTime() : Date.now()
        if (Date.now() - startedAt > timeout * 1000) {
          await db
            .from('tasks')
            .update({ status: 'FAILED', progress: 100, error_message: '视频生成等待超时', finished_at: new Date().toISOString() })
            .eq('id', task.id)
          results.push({ id: task.id, status: 'FAILED', reason: 'timeout' })
          continue
        }

        const outcome = await pollVideoOnce(config, task.provider_task_id, db, task.created_by)

        if (outcome.state === 'processing') {
          const pollCount = Number(task.result_payload?.poll_count ?? 0) + 1
          await db
            .from('tasks')
            .update({
              progress: Math.min(90, Math.max(task.progress, 20 + pollCount * 2)),
              provider_status: outcome.providerStatus,
              result_payload: { ...(task.result_payload ?? {}), poll_count: pollCount, provider_status: outcome.providerStatus },
            })
            .eq('id', task.id)
          results.push({ id: task.id, status: 'RUNNING', provider_status: outcome.providerStatus })
          continue
        }

        if (outcome.state === 'failed') {
          await db
            .from('tasks')
            .update({ status: 'FAILED', progress: 100, error_message: outcome.message, finished_at: new Date().toISOString() })
            .eq('id', task.id)
          results.push({ id: task.id, status: 'FAILED', reason: outcome.message })
          continue
        }

        // 成功：落 Storage + 写 files 表
        const mimeType = outcome.mimeType
        const extension = MIME_EXTENSIONS[mimeType] ?? '.mp4'
        const date = new Date().toISOString().slice(0, 10).replace(/-/g, '')
        const { data: storyboard } = await db
          .from('storyboards')
          .select('*')
          .eq('id', task.target_id)
          .single()
        const title = storyboard?.title ?? 'video'
        const storagePath = `generated/video/${date}/${title}-${crypto.randomUUID().slice(0, 10)}${extension}`

        const { error: uploadError } = await db.storage
          .from('media')
          .upload(storagePath, outcome.data, { contentType: mimeType })
        if (uploadError) throw new Error(`上传失败：${uploadError.message}`)

        const fileName = storagePath.split('/').pop()!
        const { data: fileRecord } = await db
          .from('files')
          .insert({
            project_id: task.project_id,
            file_name: fileName,
            original_name: fileName,
            file_type: 'VIDEO',
            mime_type: mimeType,
            file_size: outcome.data.byteLength,
            storage_bucket: 'media',
            storage_path: storagePath,
            duration: storyboard?.duration ?? 10,
            source_type: 'AI_VIDEO',
            source_id: task.id,
            created_by: task.created_by,
          })
          .select()
          .single()

        if (storyboard) {
          await db.from('storyboards').update({ status: 'GENERATED' }).eq('id', storyboard.id)
        }
        await db
          .from('tasks')
          .update({
            status: 'SUCCESS',
            progress: 100,
            provider_status: 'SUCCESS',
            result_payload: {
              ...(task.result_payload ?? {}),
              provider_status: 'SUCCESS',
              file_id: fileRecord!.id,
              storage_path: storagePath,
            },
            finished_at: new Date().toISOString(),
          })
          .eq('id', task.id)
        results.push({ id: task.id, status: 'SUCCESS', file_id: fileRecord!.id })
      } catch (error) {
        results.push({
          id: task.id,
          status: 'ERROR',
          message: error instanceof Error ? error.message : String(error),
        })
      }
    }

    return json({ polled: results.length, results })
  }),
)
