<script setup lang="ts">
import { Delete, Edit, MagicStick, Plus, Search, Tickets, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onActivated, reactive, ref } from 'vue'

import { charactersApi, errorMessage, filesApi, modelConfigsApi, projectsApi, scenesApi, scriptsApi, storyboardsApi, tasksApi } from '@/api'
import { publicUrl } from '@/lib/supabase'
import type { AiFile, Character, ModelConfig, Project, Scene, Script, Storyboard } from '@/types'

const loading = ref(false)
const saving = ref(false)
const generating = ref(false)
const dialogVisible = ref(false)
const generateVisible = ref(false)
const editingId = ref<number | null>(null)
const scripts = ref<Script[]>([])
const projects = ref<Project[]>([])
const textModels = ref<ModelConfig[]>([])
const videoModels = ref<ModelConfig[]>([])
const images = ref<AiFile[]>([])
const total = ref(0)
const filters = reactive({ keyword: '', projectId: null as number | null, page: 1, pageSize: 20 })
const form = reactive({ project_id: null as number | null, title: '', summary: '', content: '', duration: null as number | null, status: 'DRAFT' as Script['status'] })
const generateForm = reactive({ project_id: null as number | null, title: '', keywords: '', style: '', model_config_id: null as number | null })

const drawerVisible = ref(false)
const boardDialogVisible = ref(false)
const videoDialogVisible = ref(false)
const videoSubmitting = ref(false)
const videoTarget = ref<Storyboard | null>(null)
const boardSaving = ref(false)
const boardEditingId = ref<number | null>(null)
const selectedScript = ref<Script | null>(null)
const storyboards = ref<Storyboard[]>([])
const scenes = ref<Scene[]>([])
const characters = ref<Character[]>([])
const boardForm = reactive({ sequence: 1, title: '', description: '', duration: null as number | null, camera: '', dialogue: '', video_prompt: '', scene_id: null as number | null, character_ids: [] as number[], status: 'DRAFT' as Storyboard['status'] })
const videoForm = reactive({
  model_config_id: null as number | null,
  reference_file_ids: [] as number[],
  duration: 10,
  resolution: '768p竖',
  seed: null as number | null,
})
const maxReferenceImages = 9

function projectName(id: number) { return projects.value.find((item) => item.id === id)?.name || `项目 #${id}` }
function imageUrl(item: AiFile) { return item.thumbnail_path || publicUrl(item.storage_path) }
function sceneName(id: number | null) { return id ? scenes.value.find((item) => item.id === id)?.name || `场景 #${id}` : '未关联' }
function characterNames(ids: number[]) { return ids.map((id) => characters.value.find((item) => item.id === id)?.name || `#${id}`).join('、') || '未关联' }
function statusLabel(status: Script['status']) { return { DRAFT: '草稿', READY: '已就绪', ARCHIVED: '已归档' }[status] }

async function loadData() {
  loading.value = true
  try {
    const [scriptResult, projectResult, textModelResult, videoModelResult, imageResult] = await Promise.all([
      scriptsApi.list({ keyword: filters.keyword || undefined, project_id: filters.projectId || undefined, page: filters.page, page_size: filters.pageSize }),
      projectsApi.list({ page_size: 100 }),
      modelConfigsApi.list({ model_type: 'TEXT', status: 'ENABLED', page_size: 100 }),
      modelConfigsApi.list({ model_type: 'VIDEO', status: 'ENABLED', page_size: 100 }),
      filesApi.list({ file_type: 'IMAGE', page_size: 100 }),
    ])
    scripts.value = scriptResult.items
    total.value = scriptResult.total
    projects.value = projectResult.items
    textModels.value = textModelResult.items
    videoModels.value = videoModelResult.items
    images.value = imageResult.items
  } catch (error) { ElMessage.error(errorMessage(error, '剧本加载失败')) } finally { loading.value = false }
}

function openGenerate() {
  const defaultModel = textModels.value.find((item) => item.is_default) || textModels.value[0]
  Object.assign(generateForm, { project_id: filters.projectId, title: '', keywords: '', style: '', model_config_id: defaultModel?.id || null })
  generateVisible.value = true
}

async function generateScript() {
  if (!generateForm.project_id || !generateForm.title.trim() || !generateForm.keywords.trim() || !generateForm.model_config_id) return ElMessage.warning('请选择项目和文本模型，并填写剧本名称与关键词')
  generating.value = true
  try {
    await scriptsApi.generate({
      project_id: generateForm.project_id,
      model_config_id: generateForm.model_config_id,
      title: generateForm.title.trim(),
      keywords: generateForm.keywords.trim(),
      style: generateForm.style.trim() || undefined,
    })
    ElMessage.success('六段 10 秒分镜已生成')
    generateVisible.value = false
    await loadData()
  } catch (error) { ElMessage.error(errorMessage(error, '剧本分镜生成失败')) } finally { generating.value = false }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { project_id: filters.projectId, title: '', summary: '', content: '', duration: null, status: 'DRAFT' })
  dialogVisible.value = true
}
function openEdit(item: Script) {
  editingId.value = item.id
  Object.assign(form, { project_id: item.project_id, title: item.title, summary: item.summary || '', content: item.content, duration: item.duration, status: item.status })
  dialogVisible.value = true
}
async function save() {
  if (!form.project_id || !form.title.trim()) return ElMessage.warning('请选择项目并填写剧本名称')
  saving.value = true
  try {
    const payload = { project_id: form.project_id, title: form.title.trim(), summary: form.summary.trim() || null, content: form.content, duration: form.duration, status: form.status }
    if (editingId.value) await scriptsApi.update(editingId.value, payload)
    else await scriptsApi.create(payload)
    ElMessage.success(editingId.value ? '剧本已更新' : '剧本已创建')
    dialogVisible.value = false
    await loadData()
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { saving.value = false }
}
async function remove(item: Script) {
  try {
    await ElMessageBox.confirm(`确定删除剧本“${item.title}”及其全部分镜吗？`, '删除剧本', { type: 'warning' })
    await scriptsApi.remove(item.id)
    ElMessage.success('剧本已删除')
    await loadData()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorMessage(error)) }
}

async function manageStoryboards(item: Script) {
  selectedScript.value = item
  drawerVisible.value = true
  try {
    const [boardResult, sceneResult, characterResult] = await Promise.all([
      storyboardsApi.list({ script_id: item.id, page_size: 200 }),
      scenesApi.list({ project_id: item.project_id, page_size: 100 }),
      charactersApi.list({ project_id: item.project_id, page_size: 100 }),
    ])
    storyboards.value = boardResult.items
    scenes.value = sceneResult.items
    characters.value = characterResult.items
  } catch (error) { ElMessage.error(errorMessage(error, '分镜加载失败')) }
}
function openBoardCreate() {
  boardEditingId.value = null
  Object.assign(boardForm, { sequence: (storyboards.value.at(-1)?.sequence || 0) + 1, title: '', description: '', duration: null, camera: '', dialogue: '', video_prompt: '', scene_id: null, character_ids: [], status: 'DRAFT' })
  boardDialogVisible.value = true
}
function openBoardEdit(item: Storyboard) {
  boardEditingId.value = item.id
  Object.assign(boardForm, { sequence: item.sequence, title: item.title, description: item.description || '', duration: item.duration, camera: item.camera || '', dialogue: item.dialogue || '', video_prompt: item.video_prompt || '', scene_id: item.scene_id, character_ids: [...item.character_ids], status: item.status })
  boardDialogVisible.value = true
}
async function saveBoard() {
  if (!selectedScript.value || !boardForm.title.trim()) return ElMessage.warning('请填写分镜标题')
  boardSaving.value = true
  try {
    const payload = { script_id: selectedScript.value.id, project_id: selectedScript.value.project_id, sequence: boardForm.sequence, title: boardForm.title.trim(), description: boardForm.description.trim() || null, duration: boardForm.duration, camera: boardForm.camera.trim() || null, dialogue: boardForm.dialogue.trim() || null, video_prompt: boardForm.video_prompt.trim() || null, scene_id: boardForm.scene_id, character_ids: boardForm.character_ids, reference_file_ids: [], status: boardForm.status }
    if (boardEditingId.value) await storyboardsApi.update(boardEditingId.value, payload)
    else await storyboardsApi.create(payload)
    ElMessage.success(boardEditingId.value ? '分镜已更新' : '分镜已添加')
    boardDialogVisible.value = false
    await manageStoryboards(selectedScript.value)
    await loadData()
  } catch (error) { ElMessage.error(errorMessage(error)) } finally { boardSaving.value = false }
}
async function removeBoard(item: Storyboard) {
  try {
    await ElMessageBox.confirm(`确定删除分镜“${item.title}”吗？`, '删除分镜', { type: 'warning' })
    await storyboardsApi.remove(item.id)
    ElMessage.success('分镜已删除')
    if (selectedScript.value) await manageStoryboards(selectedScript.value)
    await loadData()
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorMessage(error)) }
}

function openVideoGenerate(item: Storyboard | null) {
  const defaultModel = videoModels.value.find((model) => model.is_default) || videoModels.value[0]
  videoTarget.value = item
  Object.assign(videoForm, {
    model_config_id: defaultModel?.id || null,
    reference_file_ids: [...(item?.reference_file_ids || [])].slice(0, maxReferenceImages),
    duration: Math.min(15, Math.max(1, Math.round(item?.duration || 10))),
    resolution: '768p竖',
    seed: null,
  })
  videoDialogVisible.value = true
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
  if (videoForm.reference_file_ids.length >= maxReferenceImages) {
    ElMessage.warning(`最多选择 ${maxReferenceImages} 张参考图片`)
    return
  }
  videoForm.reference_file_ids.push(fileId)
}

async function submitVideoGeneration() {
  if (!videoForm.model_config_id) return ElMessage.warning('请选择视频模型')
  const targets = videoTarget.value ? [videoTarget.value] : storyboards.value
  if (!targets.length) return ElMessage.warning('当前剧本没有可生成的分镜')
  videoSubmitting.value = true
  try {
    const payload = {
      model_config_id: videoForm.model_config_id,
      reference_file_ids: videoForm.reference_file_ids,
      duration: videoForm.duration,
      resolution: videoForm.resolution,
      seed: videoForm.seed ?? undefined,
    }
    await Promise.all(targets.map((item) => tasksApi.generateVideo({ storyboard_id: item.id, ...payload })))
    ElMessage.success(`${targets.length} 个视频生成任务已加入队列`)
    videoDialogVisible.value = false
  } catch (error) { ElMessage.error(errorMessage(error, '创建视频任务失败')) } finally { videoSubmitting.value = false }
}
function search() { filters.page = 1; loadData() }
onActivated(loadData)
</script>

<template>
  <div class="page">
    <div class="page-header"><div><h1>剧本管理</h1><p>编写剧本内容，并将故事拆分为可执行的镜头序列</p></div><div class="page-actions"><el-button :icon="Plus" @click="openCreate">手动新建</el-button><el-button type="primary" :icon="MagicStick" @click="openGenerate">AI 生成六段分镜</el-button></div></div>
    <div class="filter-bar"><el-input v-model="filters.keyword" clearable placeholder="搜索剧本名称或摘要" style="width: 260px" :prefix-icon="Search" @keyup.enter="search" /><el-select v-model="filters.projectId" clearable placeholder="全部项目" style="width: 180px" @change="search"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select><el-button @click="search">查询</el-button></div>
    <section class="content-panel table-panel">
      <el-table v-loading="loading" :data="scripts" empty-text="暂无剧本">
        <el-table-column prop="title" label="剧本名称" min-width="190" />
        <el-table-column label="归属项目" min-width="160"><template #default="{ row }">{{ projectName(row.project_id) }}</template></el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="260" show-overflow-tooltip><template #default="{ row }"><span :class="{ muted: !row.summary }">{{ row.summary || '暂无摘要' }}</span></template></el-table-column>
        <el-table-column label="时长" width="100"><template #default="{ row }">{{ row.duration ? `${row.duration} 秒` : '未设置' }}</template></el-table-column>
        <el-table-column prop="storyboard_count" label="分镜" width="80" />
        <el-table-column label="状态" width="95"><template #default="{ row }"><el-tag :type="row.status === 'READY' ? 'success' : row.status === 'ARCHIVED' ? 'info' : 'warning'" effect="plain">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="操作" width="235" fixed="right"><template #default="{ row }"><el-button text type="primary" :icon="Tickets" @click="manageStoryboards(row)">分镜</el-button><el-button text :icon="Edit" @click="openEdit(row)">编辑</el-button><el-button text type="danger" :icon="Delete" @click="remove(row)">删除</el-button></template></el-table-column>
      </el-table>
      <div class="pagination-row"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @change="loadData" /></div>
    </section>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑剧本' : '新建剧本'" width="min(760px, calc(100vw - 32px))">
      <el-form label-position="top"><div class="form-grid"><el-form-item label="归属项目" required><el-select v-model="form.project_id" placeholder="请选择项目" style="width: 100%"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="剧本名称" required><el-input v-model="form.title" maxlength="200" /></el-form-item></div><el-form-item label="摘要"><el-input v-model="form.summary" type="textarea" :rows="2" /></el-form-item><el-form-item label="剧本正文"><el-input v-model="form.content" type="textarea" :rows="10" /></el-form-item><div class="form-grid"><el-form-item label="预计时长（秒）"><el-input-number v-model="form.duration" :min="1" :max="86400" controls-position="right" style="width: 100%" /></el-form-item><el-form-item label="状态"><el-select v-model="form.status" style="width: 100%"><el-option label="草稿" value="DRAFT" /><el-option label="已就绪" value="READY" /><el-option label="已归档" value="ARCHIVED" /></el-select></el-form-item></div></el-form>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="generateVisible" title="AI 生成六段分镜" width="min(680px, calc(100vw - 32px))">
      <el-form label-position="top"><div class="form-grid"><el-form-item label="归属项目" required><el-select v-model="generateForm.project_id" placeholder="请选择项目" style="width: 100%"><el-option v-for="item in projects" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="剧本名称" required><el-input v-model="generateForm.title" maxlength="200" /></el-form-item></div><el-form-item label="故事关键词与描述" required><el-input v-model="generateForm.keywords" type="textarea" :rows="7" maxlength="5000" show-word-limit placeholder="输入人物、场景、冲突、情节走向和希望出现的关键画面" /></el-form-item><div class="form-grid"><el-form-item label="视觉风格"><el-input v-model="generateForm.style" placeholder="例如：电影感、古风写实、赛博朋克" /></el-form-item><el-form-item label="文本模型" required><el-select v-model="generateForm.model_config_id" placeholder="请选择文本模型" style="width: 100%"><el-option v-for="item in textModels" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item></div></el-form>
      <template #footer><el-button @click="generateVisible = false">取消</el-button><el-button type="primary" :icon="MagicStick" :loading="generating" @click="generateScript">生成剧本与分镜</el-button></template>
    </el-dialog>

    <el-drawer v-model="drawerVisible" :title="`${selectedScript?.title || ''} · 分镜`" size="min(1040px, 92vw)" destroy-on-close>
      <div class="drawer-toolbar"><span class="muted">共 {{ storyboards.length }} 个镜头</span><div class="page-actions"><el-button :icon="VideoPlay" :disabled="!storyboards.length" @click="openVideoGenerate(null)">全部生成视频</el-button><el-button type="primary" :icon="Plus" @click="openBoardCreate">添加分镜</el-button></div></div>
      <el-table :data="storyboards" empty-text="暂无分镜，先添加第一个镜头">
        <el-table-column prop="sequence" label="#" width="58" />
        <el-table-column prop="title" label="镜头" min-width="150" />
        <el-table-column label="场景" min-width="120"><template #default="{ row }">{{ sceneName(row.scene_id) }}</template></el-table-column>
        <el-table-column label="角色" min-width="160" show-overflow-tooltip><template #default="{ row }">{{ characterNames(row.character_ids) }}</template></el-table-column>
        <el-table-column prop="camera" label="机位 / 运镜" min-width="130"><template #default="{ row }"><span :class="{ muted: !row.camera }">{{ row.camera || '未设置' }}</span></template></el-table-column>
        <el-table-column label="时长" width="85"><template #default="{ row }">{{ row.duration ? `${row.duration} 秒` : '-' }}</template></el-table-column>
        <el-table-column label="操作" width="220" fixed="right"><template #default="{ row }"><el-button text type="primary" :icon="VideoPlay" @click="openVideoGenerate(row)">生成</el-button><el-button text :icon="Edit" @click="openBoardEdit(row)">编辑</el-button><el-button text type="danger" :icon="Delete" @click="removeBoard(row)" /></template></el-table-column>
      </el-table>
    </el-drawer>

    <el-dialog v-model="boardDialogVisible" :title="boardEditingId ? '编辑分镜' : '添加分镜'" width="min(760px, calc(100vw - 32px))" append-to-body>
      <el-form label-position="top"><div class="board-heading"><el-form-item label="序号" required><el-input-number v-model="boardForm.sequence" :min="1" controls-position="right" /></el-form-item><el-form-item label="分镜标题" required><el-input v-model="boardForm.title" /></el-form-item><el-form-item label="时长（秒）"><el-input-number v-model="boardForm.duration" :min="0.1" :step="0.5" controls-position="right" /></el-form-item></div><el-form-item label="画面描述"><el-input v-model="boardForm.description" type="textarea" :rows="3" /></el-form-item><div class="form-grid"><el-form-item label="场景"><el-select v-model="boardForm.scene_id" clearable placeholder="选择场景" style="width: 100%"><el-option v-for="item in scenes" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item><el-form-item label="角色"><el-select v-model="boardForm.character_ids" multiple collapse-tags collapse-tags-tooltip placeholder="选择角色" style="width: 100%"><el-option v-for="item in characters" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item></div><el-form-item label="机位 / 运镜"><el-input v-model="boardForm.camera" placeholder="例如：中景，缓慢推近" /></el-form-item><el-form-item label="台词 / 旁白"><el-input v-model="boardForm.dialogue" type="textarea" :rows="2" /></el-form-item><el-form-item label="视频提示词"><el-input v-model="boardForm.video_prompt" type="textarea" :rows="3" /></el-form-item><el-form-item label="状态"><el-segmented v-model="boardForm.status" :options="[{ label: '草稿', value: 'DRAFT' }, { label: '已就绪', value: 'READY' }, { label: '已生成', value: 'GENERATED' }]" /></el-form-item></el-form>
      <template #footer><el-button @click="boardDialogVisible = false">取消</el-button><el-button type="primary" :loading="boardSaving" @click="saveBoard">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="videoDialogVisible" :title="videoTarget ? `生成视频 · ${videoTarget.title}` : '生成全部分镜视频'" width="min(760px, calc(100vw - 32px))" append-to-body>
      <el-form label-position="top">
        <el-form-item label="视频模型" required><el-select v-model="videoForm.model_config_id" placeholder="请选择视频模型" style="width: 100%"><el-option v-for="item in videoModels" :key="item.id" :label="`${item.name} · ${item.model_name}`" :value="item.id" /></el-select></el-form-item>
        <div class="video-option-grid">
          <el-form-item label="视频时长（秒）"><el-input-number v-model="videoForm.duration" :min="1" :max="15" controls-position="right" style="width: 100%" /></el-form-item>
          <el-form-item label="输出分辨率"><el-select v-model="videoForm.resolution" style="width: 100%"><el-option label="480p 竖屏" value="480p竖" /><el-option label="768p 竖屏" value="768p竖" /><el-option label="480p 横屏" value="480p横" /><el-option label="768p 横屏" value="768p横" /></el-select></el-form-item>
          <el-form-item label="随机种子"><el-input-number v-model="videoForm.seed" placeholder="随机" controls-position="right" style="width: 100%" /></el-form-item>
        </div>
        <el-form-item label="参考图片">
          <div class="image-picker">
            <div class="image-picker-toolbar"><span>已选 {{ videoForm.reference_file_ids.length }} / {{ maxReferenceImages }}</span><el-button v-if="videoForm.reference_file_ids.length" text type="primary" @click="videoForm.reference_file_ids = []">清空</el-button></div>
            <el-empty v-if="!images.length" description="图片库暂无图片" :image-size="68" />
            <div v-else class="image-option-grid">
              <button v-for="item in images" :key="item.id" class="image-option" :class="{ selected: selectedImageOrder(item.id) }" type="button" :aria-label="`${selectedImageOrder(item.id) ? '取消选择' : '选择'} ${item.file_name}`" @click="toggleReferenceImage(item.id)">
                <el-image :src="imageUrl(item)" fit="cover" loading="lazy" />
                <span v-if="selectedImageOrder(item.id)" class="image-order">{{ selectedImageOrder(item.id) }}</span>
                <span class="image-name" :title="item.file_name">{{ item.file_name }}</span>
              </button>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="videoDialogVisible = false">取消</el-button><el-button type="primary" :icon="VideoPlay" :loading="videoSubmitting" @click="submitVideoGeneration">加入视频队列</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.drawer-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.board-heading { display: grid; grid-template-columns: 110px 1fr 140px; gap: 14px; }
.video-option-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.image-picker { width: 100%; overflow: hidden; border: 1px solid #dfe4e0; border-radius: 6px; }
.image-picker-toolbar { display: flex; align-items: center; justify-content: space-between; min-height: 42px; padding: 0 12px; color: #707872; font-size: 12px; border-bottom: 1px solid #e5e9e6; }
.image-option-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 10px; max-height: 320px; padding: 12px; overflow-y: auto; }
.image-option { position: relative; min-width: 0; padding: 4px; color: #424943; background: #fff; border: 1px solid #dfe4e0; border-radius: 6px; cursor: pointer; }
.image-option:hover { border-color: #84ad99; }
.image-option.selected { border-color: #2f7d5c; box-shadow: 0 0 0 2px rgb(47 125 92 / 14%); }
.image-option :deep(.el-image) { display: block; width: 100%; aspect-ratio: 1; background: #eef1ef; border-radius: 3px; }
.image-order { position: absolute; top: 8px; right: 8px; display: grid; width: 22px; height: 22px; place-items: center; color: #fff; background: #2f7d5c; border: 2px solid #fff; border-radius: 50%; font-size: 11px; font-weight: 700; }
.image-name { display: block; padding: 6px 3px 3px; overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 680px) { .form-grid, .board-heading, .video-option-grid { grid-template-columns: 1fr; gap: 0; } .image-option-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
</style>
