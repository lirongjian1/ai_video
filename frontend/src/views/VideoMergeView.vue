<script setup lang="ts">
import { ArrowDown, ArrowUp, Delete, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onActivated, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { errorMessage, http } from '@/api/http'
import type { AiFile, AiTask, PageResult, Project } from '@/types'

const router = useRouter()
const loading = ref(false)
const submitting = ref(false)
const videos = ref<AiFile[]>([])
const projects = ref<Project[]>([])
const ffmpegAvailable = ref<boolean | null>(null)
const form = reactive({ project_id: null as number | null, name: '', output_name: 'merged-video', file_ids: [] as number[] })
const selectedVideos = computed(() => form.file_ids.map((id) => videos.value.find((item) => item.id === id)).filter((item): item is AiFile => Boolean(item)))

function formatSize(size: number) { return size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} KB` : `${(size / 1024 / 1024).toFixed(1)} MB` }
function move(index: number, direction: -1 | 1) {
  const target = index + direction
  if (target < 0 || target >= form.file_ids.length) return
  const ids = [...form.file_ids]
  ;[ids[index], ids[target]] = [ids[target], ids[index]]
  form.file_ids = ids
}
function removeAt(index: number) { form.file_ids = form.file_ids.filter((_, itemIndex) => itemIndex !== index) }

async function loadData() {
  loading.value = true
  try {
    const [videoResult, projectResult, capabilityResult] = await Promise.all([
      http.get<PageResult<AiFile>>('/files', { params: { file_type: 'VIDEO', page_size: 100 } }),
      http.get<PageResult<Project>>('/projects', { params: { page_size: 100 } }),
      http.get<{ ffmpeg_available: boolean }>('/tasks/capabilities'),
    ])
    videos.value = videoResult.data.items
    projects.value = projectResult.data.items
    ffmpegAvailable.value = capabilityResult.data.ffmpeg_available
  } catch (error) { ElMessage.error(errorMessage(error, '合成数据加载失败')) } finally { loading.value = false }
}

async function submit() {
  if (!form.name.trim() || !form.output_name.trim()) return ElMessage.warning('请填写任务名称和输出名称')
  if (form.file_ids.length < 2) return ElMessage.warning('请至少选择两个视频片段')
  if (!ffmpegAvailable.value) return ElMessage.warning('当前后端未检测到 FFmpeg，暂时无法执行合成')
  submitting.value = true
  try {
    const { data } = await http.post<AiTask>('/video-merges', { project_id: form.project_id, name: form.name.trim(), output_name: form.output_name.trim(), file_ids: form.file_ids })
    if (data.status === 'FAILED') ElMessage.error(data.error_message || '合成任务创建失败')
    else {
      ElMessage.success('合成任务已创建，可在工作台查看进度')
      form.name = ''; form.output_name = 'merged-video'; form.file_ids = []
    }
  } catch (error) { ElMessage.error(errorMessage(error, '创建合成任务失败')) } finally { submitting.value = false }
}

onActivated(loadData)
</script>

<template>
  <div class="page">
    <div class="page-header"><div><h1>视频合成</h1><p>按顺序拼接本地视频片段，输出文件自动进入视频管理</p></div><div class="page-actions"><el-button @click="router.push('/')">查看进度</el-button><el-button type="primary" :icon="VideoPlay" :loading="submitting" @click="submit">开始合成</el-button></div></div>
    <el-alert v-if="ffmpegAvailable === false" title="后端未检测到 FFmpeg，请安装 FFmpeg 并加入系统 PATH，重启后端后即可执行合成。" type="warning" show-icon :closable="false" class="capability-alert" />
    <section v-loading="loading" class="content-panel merge-panel">
      <el-form label-position="top">
        <div class="form-grid"><el-form-item label="任务名称" required><el-input v-model="form.name" placeholder="例如：第一集成片" maxlength="200" /></el-form-item><el-form-item label="归属项目"><el-select v-model="form.project_id" clearable placeholder="不指定项目" style="width: 100%"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="输出文件名" required><el-input v-model="form.output_name"><template #append>.mp4</template></el-input></el-form-item></div>
        <el-form-item label="选择视频片段" required><el-select v-model="form.file_ids" multiple filterable collapse-tags collapse-tags-tooltip placeholder="至少选择两个视频" style="width: 100%"><el-option v-for="item in videos" :key="item.id" :label="item.file_name" :value="item.id" /></el-select></el-form-item>
      </el-form>
      <div class="clip-heading"><strong>合成顺序</strong><span class="muted">{{ selectedVideos.length }} 个片段</span></div>
      <el-table :data="selectedVideos" empty-text="从上方选择视频片段">
        <el-table-column label="#" width="58"><template #default="{ $index }">{{ $index + 1 }}</template></el-table-column>
        <el-table-column label="预览" width="92"><template #default="{ row }"><video :src="row.url" class="clip-preview" muted preload="metadata" /></template></el-table-column>
        <el-table-column prop="file_name" label="文件名" min-width="240" show-overflow-tooltip />
        <el-table-column label="时长" width="110"><template #default="{ row }">{{ row.duration ? `${row.duration.toFixed(1)} 秒` : '未读取' }}</template></el-table-column>
        <el-table-column label="大小" width="110"><template #default="{ row }">{{ formatSize(row.file_size) }}</template></el-table-column>
        <el-table-column label="排序" width="145" fixed="right"><template #default="{ $index }"><el-tooltip content="上移"><el-button circle text :icon="ArrowUp" :disabled="$index === 0" @click="move($index, -1)" /></el-tooltip><el-tooltip content="下移"><el-button circle text :icon="ArrowDown" :disabled="$index === selectedVideos.length - 1" @click="move($index, 1)" /></el-tooltip><el-tooltip content="移除"><el-button circle text type="danger" :icon="Delete" @click="removeAt($index)" /></el-tooltip></template></el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>.capability-alert { margin-bottom: 14px; } .merge-panel { padding: 20px; } .form-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; } .clip-heading { display: flex; align-items: center; justify-content: space-between; margin: 12px 0; } .clip-preview { display: block; width: 64px; height: 38px; object-fit: cover; background: #171a18; border-radius: 4px; } @media (max-width: 800px) { .form-grid { grid-template-columns: 1fr; gap: 0; } }</style>
