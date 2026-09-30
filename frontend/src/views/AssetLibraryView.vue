<script setup lang="ts">
import { CopyDocument, Delete, Download, Edit, MagicStick, Plus, Search, VideoPlay, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type UploadUserFile } from 'element-plus'
import { computed, onActivated, reactive, ref, watch } from 'vue'

import { errorMessage, filesApi, modelConfigsApi, projectsApi, promptsApi, publicUrl, scriptsApi, storyboardsApi, tasksApi } from '@/api'
import { supabase } from '@/lib/supabase'
import type { AiFile, ModelConfig, Project, Prompt, Script, Storyboard } from '@/types'

/** filesApi 未暴露重命名方法，这里直接更新 files.file_name。 */
async function renameStoredFile(id: number, fileName: string) {
  const { error } = await supabase.from('files').update({ file_name: fileName }).eq('id', id)
  if (error) throw new Error(error.message)
}

const props = defineProps<{ fileType: 'IMAGE' | 'VIDEO' }>()
const isImage = computed(() => props.fileType === 'IMAGE')
const title = computed(() => isImage.value ? '图片管理' : '视频管理')
const noun = computed(() => isImage.value ? '图片' : '视频')
const loading = ref(false)
const uploading = ref(false)
const generating = ref(false)
const uploadVisible = ref(false)
const generateVisible = ref(false)
const previewVisible = ref(false)
const previewFile = ref<AiFile | null>(null)
const uploadFiles = ref<UploadUserFile[]>([])
const uploadProjectId = ref<number | null>(null)
const files = ref<AiFile[]>([])
const projects = ref<Project[]>([])
const prompts = ref<Prompt[]>([])
const imageModels = ref<ModelConfig[]>([])
const videoModels = ref<ModelConfig[]>([])
const libraryImages = ref<AiFile[]>([])
const scripts = ref<Script[]>([])
const storyboards = ref<Storyboard[]>([])
const total = ref(0)
const filters = reactive({ keyword: '', sourceType: '', projectId: null as number | null, page: 1, pageSize: 20 })
const generateForm = reactive({ project_id: null as number | null, prompt_id: null as number | null, name: '', model_config_id: null as number | null, size: '1024x1024' })
const videoGenerateVisible = ref(false)
const videoGenerating = ref(false)
const maxReferenceImages = 9
const videoForm = reactive({
  project_id: null as number | null,
  storyboard_id: null as number | null,
  model_config_id: null as number | null,
  reference_file_ids: [] as number[],
  duration: 10,
  resolution: '768p竖',
  seed: null as number | null,
})
const sourceLabels: Record<AiFile['source_type'], string> = { UPLOAD: '手动上传', AI_IMAGE: 'AI 生成', AI_VIDEO: 'AI 生成', VIDEO_MERGE: '视频合成' }
const availableStoryboards = computed(() => storyboards.value.filter((item) => !videoForm.project_id || item.project_id === videoForm.project_id))

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
function projectName(id: number | null) { return id ? projects.value.find((item) => item.id === id)?.name || `项目 #${id}` : '公共素材' }

async function loadData() {
  loading.value = true
  try {
    const [fileResult, projectResult, promptResult, modelResult, videoOptions] = await Promise.all([
      filesApi.list({ keyword: filters.keyword || undefined, file_type: props.fileType, source_type: filters.sourceType || undefined, project_id: filters.projectId || undefined, page: filters.page, page_size: filters.pageSize }),
      projectsApi.list({ page_size: 100 }),
      promptsApi.list({ status: 'ENABLED', page_size: 100 }),
      modelConfigsApi.list({ model_type: 'IMAGE', status: 'ENABLED', page_size: 100 }),
      isImage.value ? Promise.resolve(null) : Promise.all([
        modelConfigsApi.list({ model_type: 'VIDEO', status: 'ENABLED', page_size: 100 }),
        filesApi.list({ file_type: 'IMAGE', page_size: 100 }),
        scriptsApi.list({ page_size: 100 }),
        storyboardsApi.list({ page_size: 200 }),
      ]),
    ])
    files.value = fileResult.items
    total.value = fileResult.total
    projects.value = projectResult.items
    prompts.value = promptResult.items
    imageModels.value = modelResult.items
    if (videoOptions) {
      videoModels.value = videoOptions[0].items
      libraryImages.value = videoOptions[1].items
      scripts.value = videoOptions[2].items
      storyboards.value = videoOptions[3].items
    }
  } catch (error) { ElMessage.error(errorMessage(error, `${noun.value}加载失败`)) } finally { loading.value = false }
}

function scriptName(scriptId: number) { return scripts.value.find((item) => item.id === scriptId)?.title || `剧本 #${scriptId}` }

function openVideoGenerate() {
  const defaultModel = videoModels.value.find((item) => item.is_default) || videoModels.value[0]
  Object.assign(videoForm, {
    project_id: filters.projectId,
    storyboard_id: null,
    model_config_id: defaultModel?.id || null,
    reference_file_ids: [],
    duration: 10,
    resolution: '768p竖',
    seed: null,
  })
  videoGenerateVisible.value = true
}

function videoProjectChanged() {
  videoForm.storyboard_id = null
}

function videoStoryboardChanged(storyboardId: number | null) {
  const storyboard = storyboards.value.find((item) => item.id === storyboardId)
  if (!storyboard) return
  videoForm.project_id = storyboard.project_id
  videoForm.reference_file_ids = [...storyboard.reference_file_ids].slice(0, maxReferenceImages)
  videoForm.duration = Math.min(15, Math.max(1, Math.round(storyboard.duration || 10)))
}

function selectedImageOrder(fileId: number) {
  const index = videoForm.reference_file_ids.indexOf(fileId)
  return index < 0 ? 0 : index + 1
}

function toggleReferenceImage(fileId: number) {
  const index = videoForm.reference_file_ids.indexOf(fileId)
  if (index >= 0) {
    videoForm.reference_file_ids.splice(index, 1)
    return
  }
  if (videoForm.reference_file_ids.length >= maxReferenceImages) return ElMessage.warning(`最多选择 ${maxReferenceImages} 张参考图片`)
  videoForm.reference_file_ids.push(fileId)
}

async function submitVideoGeneration() {
  const storyboardId = videoForm.storyboard_id
  const modelConfigId = videoForm.model_config_id
  if (!storyboardId || !modelConfigId) return ElMessage.warning('请选择分镜和视频模型')
  videoGenerating.value = true
  try {
    await tasksApi.generateVideo({
      storyboard_id: storyboardId,
      model_config_id: modelConfigId,
      reference_file_ids: videoForm.reference_file_ids,
      duration: videoForm.duration,
      resolution: videoForm.resolution,
      seed: videoForm.seed ?? undefined,
    })
    ElMessage.success('视频生成任务已加入队列')
    videoGenerateVisible.value = false
  } catch (error) { ElMessage.error(errorMessage(error, '创建视频任务失败')) } finally { videoGenerating.value = false }
}

function openGenerate() {
  const defaultModel = imageModels.value.find((item) => item.is_default) || imageModels.value[0]
  Object.assign(generateForm, { project_id: filters.projectId, prompt_id: null, name: '', model_config_id: defaultModel?.id || null, size: '1024x1024' })
  generateVisible.value = true
}

function promptChanged(promptId: number | null) {
  const prompt = prompts.value.find((item) => item.id === promptId)
  if (prompt?.project_id && !generateForm.project_id) generateForm.project_id = prompt.project_id
  if (prompt && !generateForm.name) generateForm.name = prompt.name
}

async function submitGeneration() {
  const promptId = generateForm.prompt_id
  const modelConfigId = generateForm.model_config_id
  if (!promptId || !modelConfigId || !generateForm.name.trim()) return ElMessage.warning('请选择提示词和图片模型，并填写图片名称')
  generating.value = true
  try {
    await tasksApi.generateImage({ prompt_id: promptId, model_config_id: modelConfigId, project_id: generateForm.project_id, name: generateForm.name.trim(), size: generateForm.size })
    ElMessage.success('图片生成任务已加入队列')
    generateVisible.value = false
  } catch (error) { ElMessage.error(errorMessage(error, '创建图片任务失败')) } finally { generating.value = false }
}

async function submitUpload() {
  const raw = uploadFiles.value[0]?.raw
  if (!raw) return ElMessage.warning(`请选择${noun.value}`)
  if (!raw.type.startsWith(isImage.value ? 'image/' : 'video/')) return ElMessage.warning(`请选择有效的${noun.value}文件`)
  uploading.value = true
  try {
    await filesApi.upload(raw, uploadProjectId.value)
    ElMessage.success(`${noun.value}上传成功`)
    uploadVisible.value = false
    uploadFiles.value = []
    uploadProjectId.value = null
    await loadData()
  } catch (error) { ElMessage.error(errorMessage(error, '上传失败')) } finally { uploading.value = false }
}

async function rename(item: AiFile) {
  try {
    const result = await ElMessageBox.prompt('请输入新的显示名称', '重命名', { inputValue: item.file_name, inputPattern: /\S+/, inputErrorMessage: '名称不能为空' })
    await renameStoredFile(item.id, result.value)
    ElMessage.success('名称已更新')
    await loadData()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorMessage(error)) }
}

async function remove(item: AiFile) {
  try {
    await ElMessageBox.confirm(`确定删除“${item.file_name}”吗？磁盘文件也会被移除。`, `删除${noun.value}`, { type: 'warning' })
    await filesApi.remove(item)
    ElMessage.success(`${noun.value}已删除`)
    await loadData()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorMessage(error)) }
}

function preview(item: AiFile) { previewFile.value = item; previewVisible.value = true }
async function download(item: AiFile) {
  try {
    const href = publicUrl(item.storage_path)
    if (!href) return ElMessage.warning('文件地址不可用')
    const link = document.createElement('a'); link.href = href; link.download = item.file_name; link.target = '_blank'; link.rel = 'noopener'; link.click()
  } catch (error) { ElMessage.error(errorMessage(error, '下载失败')) }
}
async function copyUrl(item: AiFile) {
  const href = publicUrl(item.storage_path)
  if (!href) return ElMessage.warning('文件地址不可用')
  await navigator.clipboard.writeText(href)
  ElMessage.success('地址已复制')
}
function search() { filters.page = 1; loadData() }
watch(() => props.fileType, () => { filters.page = 1; loadData() })
onActivated(loadData)
</script>

<template>
  <div class="page">
    <div class="page-header"><div><h1>{{ title }}</h1><p>管理上传、AI 生成与工作流产出的{{ noun }}资产</p></div><div class="page-actions"><el-button :icon="Plus" @click="uploadVisible = true">上传{{ noun }}</el-button><el-button v-if="isImage" type="primary" :icon="MagicStick" @click="openGenerate">AI 生成图片</el-button><el-button v-else type="primary" :icon="VideoPlay" @click="openVideoGenerate">AI 生成视频</el-button></div></div>
    <div class="filter-bar"><el-input v-model="filters.keyword" clearable :placeholder="`搜索${noun}名称`" style="width: 240px" :prefix-icon="Search" @keyup.enter="search" /><el-select v-model="filters.projectId" clearable placeholder="全部项目" style="width: 180px" @change="search"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select><el-select v-model="filters.sourceType" clearable placeholder="全部来源" style="width: 150px" @change="search"><el-option label="手动上传" value="UPLOAD" /><el-option v-if="isImage" label="AI 生成" value="AI_IMAGE" /><el-option v-else label="AI 生成" value="AI_VIDEO" /><el-option v-if="!isImage" label="视频合成" value="VIDEO_MERGE" /></el-select><el-button @click="search">查询</el-button></div>
    <section class="content-panel table-panel">
      <el-table v-loading="loading" :data="files" :empty-text="`暂无${noun}`">
        <el-table-column label="预览" width="76"><template #default="{ row }"><el-image v-if="isImage" :src="publicUrl(row.storage_path)" fit="cover" class="asset-thumb" :preview-src-list="[publicUrl(row.storage_path)]" preview-teleported /><button v-else class="video-thumb" type="button" title="播放视频" @click="preview(row)"><el-icon><View /></el-icon></button></template></el-table-column>
        <el-table-column prop="file_name" :label="`${noun}名称`" min-width="220" show-overflow-tooltip />
        <el-table-column label="归属项目" min-width="150"><template #default="{ row }">{{ projectName(row.project_id) }}</template></el-table-column>
        <el-table-column label="规格" width="140"><template #default="{ row }"><span v-if="isImage && row.width">{{ row.width }} × {{ row.height }}</span><span v-else-if="!isImage && row.duration">{{ row.duration.toFixed(1) }} 秒</span><span v-else class="muted">未读取</span></template></el-table-column>
        <el-table-column label="大小" width="110"><template #default="{ row }">{{ formatSize(row.file_size) }}</template></el-table-column>
        <el-table-column label="来源" width="110"><template #default="{ row }">{{ sourceLabels[row.source_type as AiFile['source_type']] }}</template></el-table-column>
        <el-table-column label="创建时间" width="180"><template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template></el-table-column>
        <el-table-column label="操作" width="250" fixed="right"><template #default="{ row }"><el-button text type="primary" :icon="View" @click="preview(row)">预览</el-button><el-button text :icon="Edit" @click="rename(row)">重命名</el-button><el-dropdown><el-button text>更多</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item :icon="Download" @click="download(row)">下载</el-dropdown-item><el-dropdown-item :icon="CopyDocument" @click="copyUrl(row)">复制地址</el-dropdown-item><el-dropdown-item :icon="Delete" class="danger-text" @click="remove(row)">删除</el-dropdown-item></el-dropdown-menu></template></el-dropdown></template></el-table-column>
      </el-table>
      <div class="pagination-row"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @change="loadData" /></div>
    </section>
    <el-dialog v-model="uploadVisible" :title="`上传${noun}`" width="min(520px, calc(100vw - 32px))">
      <el-form label-position="top"><el-form-item label="归属项目"><el-select v-model="uploadProjectId" clearable placeholder="公共素材" style="width: 100%"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item :label="noun" required><el-upload v-model:file-list="uploadFiles" drag :auto-upload="false" :limit="1" :accept="isImage ? 'image/*' : 'video/*'" style="width: 100%"><el-icon class="upload-icon"><Plus /></el-icon><div>点击或拖拽文件到这里</div></el-upload></el-form-item></el-form>
      <template #footer><el-button @click="uploadVisible = false">取消</el-button><el-button type="primary" :loading="uploading" @click="submitUpload">上传</el-button></template>
    </el-dialog>
    <el-dialog v-if="isImage" v-model="generateVisible" title="AI 生成图片" width="min(620px, calc(100vw - 32px))">
      <el-form label-position="top">
        <el-form-item label="提示词" required><el-select v-model="generateForm.prompt_id" filterable placeholder="从提示词管理中选择" style="width: 100%" @change="promptChanged"><el-option v-for="item in prompts" :key="item.id" :label="`${item.name} · ${item.content.slice(0, 40)}`" :value="item.id" /></el-select></el-form-item>
        <div class="generate-grid"><el-form-item label="图片名称" required><el-input v-model="generateForm.name" maxlength="200" /></el-form-item><el-form-item label="归属项目"><el-select v-model="generateForm.project_id" clearable placeholder="跟随提示词" style="width: 100%"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item></div>
        <div class="generate-grid"><el-form-item label="图片模型" required><el-select v-model="generateForm.model_config_id" placeholder="请选择图片模型" style="width: 100%"><el-option v-for="item in imageModels" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="图片尺寸"><el-select v-model="generateForm.size" style="width: 100%"><el-option label="1024 × 1024" value="1024x1024" /><el-option label="1536 × 1024" value="1536x1024" /><el-option label="1024 × 1536" value="1024x1536" /></el-select></el-form-item></div>
      </el-form>
      <template #footer><el-button @click="generateVisible = false">取消</el-button><el-button type="primary" :icon="MagicStick" :loading="generating" @click="submitGeneration">加入生成队列</el-button></template>
    </el-dialog>
    <el-dialog v-if="!isImage" v-model="videoGenerateVisible" title="AI 生成视频" width="min(780px, calc(100vw - 32px))">
      <el-form label-position="top">
        <div class="generate-grid"><el-form-item label="归属项目"><el-select v-model="videoForm.project_id" clearable placeholder="全部项目" style="width: 100%" @change="videoProjectChanged"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="视频分镜" required><el-select v-model="videoForm.storyboard_id" filterable placeholder="选择包含视频提示词的分镜" style="width: 100%" @change="videoStoryboardChanged"><el-option v-for="item in availableStoryboards" :key="item.id" :label="`${scriptName(item.script_id)} · ${item.sequence}. ${item.title}`" :value="item.id" /></el-select></el-form-item></div>
        <el-form-item label="视频模型" required><el-select v-model="videoForm.model_config_id" placeholder="请选择视频模型" style="width: 100%"><el-option v-for="item in videoModels" :key="item.id" :label="`${item.name} · ${item.model_name}`" :value="item.id" /></el-select></el-form-item>
        <div class="video-option-grid"><el-form-item label="视频时长（秒）"><el-input-number v-model="videoForm.duration" :min="1" :max="15" controls-position="right" style="width: 100%" /></el-form-item><el-form-item label="输出分辨率"><el-select v-model="videoForm.resolution" style="width: 100%"><el-option label="480p 竖屏" value="480p竖" /><el-option label="768p 竖屏" value="768p竖" /><el-option label="480p 横屏" value="480p横" /><el-option label="768p 横屏" value="768p横" /></el-select></el-form-item><el-form-item label="随机种子"><el-input-number v-model="videoForm.seed" placeholder="随机" controls-position="right" style="width: 100%" /></el-form-item></div>
        <el-form-item label="参考图片">
          <div class="image-picker"><div class="image-picker-toolbar"><span>已选 {{ videoForm.reference_file_ids.length }} / {{ maxReferenceImages }}</span><el-button v-if="videoForm.reference_file_ids.length" text type="primary" @click="videoForm.reference_file_ids = []">清空</el-button></div><el-empty v-if="!libraryImages.length" description="图片库暂无图片" :image-size="68" /><div v-else class="image-option-grid"><button v-for="item in libraryImages" :key="item.id" class="image-option" :class="{ selected: selectedImageOrder(item.id) }" type="button" :aria-label="`${selectedImageOrder(item.id) ? '取消选择' : '选择'} ${item.file_name}`" @click="toggleReferenceImage(item.id)"><el-image :src="publicUrl(item.thumbnail_path || item.storage_path)" fit="cover" loading="lazy" /><span v-if="selectedImageOrder(item.id)" class="image-order">{{ selectedImageOrder(item.id) }}</span><span class="image-name" :title="item.file_name">{{ item.file_name }}</span></button></div></div>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="videoGenerateVisible = false">取消</el-button><el-button type="primary" :icon="VideoPlay" :loading="videoGenerating" @click="submitVideoGeneration">加入视频队列</el-button></template>
    </el-dialog>
    <el-dialog v-model="previewVisible" :title="previewFile?.file_name" width="min(900px, calc(100vw - 32px))" destroy-on-close><div class="preview-stage"><img v-if="isImage && previewFile" :src="publicUrl(previewFile.storage_path)" :alt="previewFile.file_name" /><video v-else-if="previewFile" :src="publicUrl(previewFile.storage_path)" controls autoplay /></div></el-dialog>
  </div>
</template>

<style scoped>
.asset-thumb, .video-thumb { width: 42px; height: 42px; border-radius: 4px; }
.video-thumb { display: grid; place-items: center; color: #fff; background: #3a423d; border: 0; cursor: pointer; }
.upload-icon { margin-bottom: 8px; font-size: 24px; }
.generate-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.video-option-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.image-picker { width: 100%; overflow: hidden; border: 1px solid #dfe4e0; border-radius: 6px; }
.image-picker-toolbar { display: flex; align-items: center; justify-content: space-between; min-height: 42px; padding: 0 12px; color: #707872; font-size: 12px; border-bottom: 1px solid #e5e9e6; }
.image-option-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 10px; max-height: 300px; padding: 12px; overflow-y: auto; }
.image-option { position: relative; min-width: 0; padding: 4px; color: #424943; background: #fff; border: 1px solid #dfe4e0; border-radius: 6px; cursor: pointer; }
.image-option:hover { border-color: #84ad99; }
.image-option.selected { border-color: #2f7d5c; box-shadow: 0 0 0 2px rgb(47 125 92 / 14%); }
.image-option :deep(.el-image) { display: block; width: 100%; aspect-ratio: 1; background: #eef1ef; border-radius: 3px; }
.image-order { position: absolute; top: 8px; right: 8px; display: grid; width: 22px; height: 22px; place-items: center; color: #fff; background: #2f7d5c; border: 2px solid #fff; border-radius: 50%; font-size: 11px; font-weight: 700; }
.image-name { display: block; padding: 6px 3px 3px; overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.preview-stage { display: grid; min-height: 260px; max-height: 70vh; place-items: center; overflow: hidden; background: #171a18; border-radius: 6px; }
.preview-stage img, .preview-stage video { display: block; max-width: 100%; max-height: 70vh; object-fit: contain; }
@media (max-width: 620px) { .generate-grid, .video-option-grid { grid-template-columns: 1fr; gap: 0; } .image-option-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
</style>
