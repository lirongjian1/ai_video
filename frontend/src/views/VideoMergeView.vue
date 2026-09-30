<script setup lang="ts">
import { ArrowDown, ArrowUp, Delete, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onActivated, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { errorMessage, filesApi, projectsApi, publicUrl } from '@/api'
import type { AiFile, Project } from '@/types'

const router = useRouter()
const loading = ref(false)
const submitting = ref(false)
const videos = ref<AiFile[]>([])
const projects = ref<Project[]>([])
const progressText = ref('')
const progressPercent = ref(0)
const form = reactive({ project_id: null as number | null, name: '', output_name: 'merged-video', file_ids: [] as number[] })

const selectedVideos = computed(() =>
  form.file_ids
    .map((id) => videos.value.find((item) => item.id === id))
    .filter((item): item is AiFile => Boolean(item)),
)

function formatSize(size: number) {
  return size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`
}
function move(index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= form.file_ids.length) return
  const ids = [...form.file_ids]
  ;[ids[index], ids[target]] = [ids[target], ids[index]]
  form.file_ids = ids
}
function removeAt(index: number) {
  form.file_ids = form.file_ids.filter((_, itemIndex) => itemIndex !== index)
}

async function loadData() {
  loading.value = true
  try {
    const [videoResult, projectResult] = await Promise.all([
      filesApi.list({ file_type: 'VIDEO', page_size: 100 }),
      projectsApi.list({ page_size: 100 }),
    ])
    videos.value = videoResult.items
    projects.value = projectResult.items
  } catch (error) {
    ElMessage.error(errorMessage(error, '合成数据加载失败'))
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!form.name.trim() || !form.output_name.trim()) return ElMessage.warning('请填写任务名称和输出名称')
  if (form.file_ids.length < 2) return ElMessage.warning('请至少选择两个视频片段')

  submitting.value = true
  progressPercent.value = 0
  progressText.value = '准备中'
  try {
    // 动态引入，避免首屏加载 MediaBunny 大包
    const { mergeVideos } = await import('@/lib/mediabunny')

    const urls = selectedVideos.value.map((item) => publicUrl(item.storage_path))
    if (urls.some((url) => !url)) throw new Error('存在无法访问的视频地址')

    const blob = await mergeVideos(urls, {
      onProgress: (progress) => {
        progressPercent.value = Math.round((progress.current / progress.total) * 100)
        progressText.value = progress.message
      },
    })

    progressText.value = '上传合成结果'
    await filesApi.registerMerged(blob, form.output_name.trim(), form.project_id)
    progressPercent.value = 100

    ElMessage.success('合成完成，已保存到视频资产库')
    form.name = ''
    form.output_name = 'merged-video'
    form.file_ids = []
    await loadData()
  } catch (error) {
    const message = errorMessage(error, '视频合成失败')
    await ElMessageBox.alert(message, '合成失败', { type: 'error', confirmButtonText: '知道了' }).catch(() => undefined)
  } finally {
    submitting.value = false
    progressText.value = ''
    progressPercent.value = 0
  }
}

onActivated(loadData)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1>视频合成</h1>
        <p>按顺序拼接视频片段，全程在浏览器本地完成，输出自动进入视频资产库</p>
      </div>
      <div class="page-actions">
        <el-button @click="router.push('/')">查看进度</el-button>
        <el-button type="primary" :icon="VideoPlay" :loading="submitting" @click="submit">开始合成</el-button>
      </div>
    </div>

    <el-alert
      v-if="submitting && progressText"
      :title="progressText"
      type="info"
      show-icon
      :closable="false"
      class="capability-alert"
    >
      <el-progress :percentage="progressPercent" :stroke-width="10" />
    </el-alert>

    <section v-loading="loading" class="content-panel merge-panel">
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="任务名称" required>
            <el-input v-model="form.name" placeholder="例如：第一集成片" maxlength="200" />
          </el-form-item>
          <el-form-item label="归属项目">
            <el-select v-model="form.project_id" clearable placeholder="不指定项目" style="width: 100%">
              <el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="输出文件名" required>
            <el-input v-model="form.output_name">
              <template #append>.mp4</template>
            </el-input>
          </el-form-item>
        </div>
        <el-form-item label="选择视频片段" required>
          <el-select
            v-model="form.file_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="至少选择两个视频"
            style="width: 100%"
          >
            <el-option v-for="item in videos" :key="item.id" :label="item.file_name" :value="item.id" />
          </el-select>
        </el-form-item>
      </el-form>

      <div class="clip-heading">
        <strong>合成顺序</strong>
        <span class="muted">{{ selectedVideos.length }} 个片段</span>
      </div>
      <el-table :data="selectedVideos" empty-text="从上方选择视频片段">
        <el-table-column label="#" width="58">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column label="预览" width="92">
          <template #default="{ row }">
            <video :src="publicUrl(row.storage_path)" class="clip-preview" muted preload="metadata" />
          </template>
        </el-table-column>
        <el-table-column prop="file_name" label="文件名" min-width="240" show-overflow-tooltip />
        <el-table-column label="时长" width="110">
          <template #default="{ row }">{{ row.duration ? `${row.duration.toFixed(1)} 秒` : '未读取' }}</template>
        </el-table-column>
        <el-table-column label="大小" width="110">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column label="排序" width="145" fixed="right">
          <template #default="{ $index }">
            <el-tooltip content="上移">
              <el-button circle text :icon="ArrowUp" :disabled="$index === 0" @click="move($index, -1)" />
            </el-tooltip>
            <el-tooltip content="下移">
              <el-button
                circle
                text
                :icon="ArrowDown"
                :disabled="$index === selectedVideos.length - 1"
                @click="move($index, 1)"
              />
            </el-tooltip>
            <el-tooltip content="移除">
              <el-button circle text type="danger" :icon="Delete" @click="removeAt($index)" />
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>

      <el-alert
        type="warning"
        show-icon
        :closable="false"
        class="tip-alert"
        title="拼接要求所有片段编码格式一致；若不一致会提示先统一转码。"
      />
    </section>
  </div>
</template>

<style scoped>
.capability-alert { margin-bottom: 14px; }
.merge-panel { padding: 20px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }
.clip-heading { display: flex; align-items: center; justify-content: space-between; margin: 12px 0; }
.clip-preview { display: block; width: 64px; height: 38px; object-fit: cover; background: #171a18; border-radius: 4px; }
.tip-alert { margin-top: 16px; }
@media (max-width: 800px) {
  .form-grid { grid-template-columns: 1fr; gap: 0; }
}
</style>
