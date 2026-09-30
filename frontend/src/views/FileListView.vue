<script setup lang="ts">
import { CopyDocument, Delete, Download, Edit, Plus, Search, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type UploadUserFile } from 'element-plus'
import { onActivated, reactive, ref } from 'vue'

import { errorMessage, filesApi, projectsApi, publicUrl } from '@/api'
import { supabase } from '@/lib/supabase'
import type { AiFile, Project } from '@/types'

/** filesApi 未暴露重命名方法，这里直接更新 files.file_name。 */
async function renameStoredFile(id: number, fileName: string) {
  const { error } = await supabase.from('files').update({ file_name: fileName }).eq('id', id)
  if (error) throw new Error(error.message)
}

const loading = ref(false)
const uploading = ref(false)
const uploadVisible = ref(false)
const previewVisible = ref(false)
const previewFile = ref<AiFile | null>(null)
const uploadFiles = ref<UploadUserFile[]>([])
const uploadProjectId = ref<number | null>(null)
const files = ref<AiFile[]>([])
const projects = ref<Project[]>([])
const total = ref(0)
const filters = reactive({ keyword: '', fileType: '', sourceType: '', projectId: null as number | null, page: 1, pageSize: 20 })

function fileSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

async function loadFiles() {
  loading.value = true
  try {
    const data = await filesApi.list({
      keyword: filters.keyword || undefined,
      file_type: filters.fileType || undefined,
      source_type: filters.sourceType || undefined,
      project_id: filters.projectId || undefined,
      page: filters.page,
      page_size: filters.pageSize,
    })
    files.value = data.items
    total.value = data.total
  } catch (error) {
    ElMessage.error(errorMessage(error, '文件加载失败'))
  } finally {
    loading.value = false
  }
}

async function loadProjects() {
  try {
    const data = await projectsApi.list({ page_size: 100 })
    projects.value = data.items
  } catch {
    projects.value = []
  }
}

function search() {
  filters.page = 1
  loadFiles()
}

async function submitUpload() {
  const raw = uploadFiles.value[0]?.raw
  if (!raw) return ElMessage.warning('请选择图片或视频')
  uploading.value = true
  try {
    await filesApi.upload(raw, uploadProjectId.value)
    ElMessage.success('文件上传成功')
    uploadVisible.value = false
    uploadFiles.value = []
    uploadProjectId.value = null
    await loadFiles()
  } catch (error) {
    ElMessage.error(errorMessage(error, '上传失败'))
  } finally {
    uploading.value = false
  }
}

async function renameFile(file: AiFile) {
  try {
    const result = await ElMessageBox.prompt('请输入新的显示名称', '重命名', {
      inputValue: file.file_name,
      inputPattern: /\S+/,
      inputErrorMessage: '文件名不能为空',
    })
    await renameStoredFile(file.id, result.value)
    ElMessage.success('文件已重命名')
    await loadFiles()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorMessage(error))
  }
}

async function deleteFile(file: AiFile) {
  try {
    await ElMessageBox.confirm(`确定删除“${file.file_name}”吗？磁盘文件也会被移除。`, '删除文件', { type: 'warning' })
    await filesApi.remove(file)
    ElMessage.success('文件已删除')
    await loadFiles()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorMessage(error))
  }
}

function showPreview(file: AiFile) {
  previewFile.value = file
  previewVisible.value = true
}

async function downloadFile(file: AiFile) {
  try {
    const href = publicUrl(file.storage_path)
    if (!href) return ElMessage.warning('文件地址不可用')
    const link = document.createElement('a')
    link.href = href
    link.download = file.file_name
    link.target = '_blank'
    link.rel = 'noopener'
    link.click()
  } catch (error) {
    ElMessage.error(errorMessage(error, '下载失败'))
  }
}

async function copyUrl(file: AiFile) {
  const href = publicUrl(file.storage_path)
  if (!href) return ElMessage.warning('文件地址不可用')
  await navigator.clipboard.writeText(href)
  ElMessage.success('地址已复制')
}

onActivated(() => {
  loadFiles()
  loadProjects()
})
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div><h1>文件管理</h1><p>统一管理上传与 AI 生成的图片、视频资产</p></div>
      <div class="page-actions"><el-button type="primary" :icon="Plus" @click="uploadVisible = true">上传文件</el-button></div>
    </div>

    <div class="filter-bar">
      <el-input v-model="filters.keyword" clearable placeholder="搜索文件名" style="width: 240px" :prefix-icon="Search" @keyup.enter="search" />
      <el-select v-model="filters.projectId" clearable placeholder="全部项目" style="width: 180px" @change="search">
        <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
      </el-select>
      <el-select v-model="filters.fileType" clearable placeholder="全部类型" style="width: 135px" @change="search">
        <el-option label="图片" value="IMAGE" /><el-option label="视频" value="VIDEO" />
      </el-select>
      <el-select v-model="filters.sourceType" clearable placeholder="全部来源" style="width: 150px" @change="search">
        <el-option label="手动上传" value="UPLOAD" /><el-option label="AI 图片" value="AI_IMAGE" /><el-option label="AI 视频" value="AI_VIDEO" /><el-option label="视频合成" value="VIDEO_MERGE" />
      </el-select>
      <el-button @click="search">查询</el-button>
    </div>

    <section class="content-panel table-panel">
      <el-table v-loading="loading" :data="files" empty-text="暂无文件">
        <el-table-column label="预览" width="76">
          <template #default="{ row }">
            <el-image v-if="row.file_type === 'IMAGE'" :src="publicUrl(row.storage_path)" fit="cover" class="file-thumb" :preview-src-list="[publicUrl(row.storage_path)]" preview-teleported />
            <button v-else class="video-thumb" type="button" title="播放视频" @click="showPreview(row)"><el-icon><View /></el-icon></button>
          </template>
        </el-table-column>
        <el-table-column prop="file_name" label="文件名" min-width="220" show-overflow-tooltip />
        <el-table-column label="类型" width="90"><template #default="{ row }"><el-tag effect="plain" :type="row.file_type === 'IMAGE' ? 'success' : 'warning'">{{ row.file_type === 'IMAGE' ? '图片' : '视频' }}</el-tag></template></el-table-column>
        <el-table-column label="大小" width="110"><template #default="{ row }">{{ fileSize(row.file_size) }}</template></el-table-column>
        <el-table-column label="来源" width="120"><template #default="{ row }">{{ { UPLOAD: '手动上传', AI_IMAGE: 'AI 图片', AI_VIDEO: 'AI 视频', VIDEO_MERGE: '视频合成' }[row.source_type as AiFile['source_type']] }}</template></el-table-column>
        <el-table-column label="创建时间" width="180"><template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template></el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" :icon="View" @click="showPreview(row)">预览</el-button>
            <el-button text :icon="Edit" @click="renameFile(row)">重命名</el-button>
            <el-dropdown>
              <el-button text>更多</el-button>
              <template #dropdown><el-dropdown-menu>
                <el-dropdown-item :icon="Download" @click="downloadFile(row)">下载</el-dropdown-item>
                <el-dropdown-item :icon="CopyDocument" @click="copyUrl(row)">复制地址</el-dropdown-item>
                <el-dropdown-item :icon="Delete" class="danger-text" @click="deleteFile(row)">删除</el-dropdown-item>
              </el-dropdown-menu></template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-row"><el-pagination v-model:current-page="filters.page" v-model:page-size="filters.pageSize" :total="total" :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next" @change="loadFiles" /></div>
    </section>

    <el-dialog v-model="uploadVisible" title="上传文件" width="min(520px, calc(100vw - 32px))">
      <el-form label-position="top">
        <el-form-item label="归属项目"><el-select v-model="uploadProjectId" clearable placeholder="公共素材（可不选）" style="width: 100%"><el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" /></el-select></el-form-item>
        <el-form-item label="图片或视频" required>
          <el-upload v-model:file-list="uploadFiles" drag :auto-upload="false" :limit="1" accept="image/*,video/*" style="width: 100%">
            <el-icon class="upload-icon"><Plus /></el-icon><div>点击或拖拽文件到这里</div>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="uploadVisible = false">取消</el-button><el-button type="primary" :loading="uploading" @click="submitUpload">上传</el-button></template>
    </el-dialog>

    <el-dialog v-model="previewVisible" :title="previewFile?.file_name" width="min(900px, calc(100vw - 32px))" destroy-on-close>
      <div class="preview-stage">
        <img v-if="previewFile?.file_type === 'IMAGE'" :src="publicUrl(previewFile.storage_path)" :alt="previewFile.file_name" />
        <video v-else-if="previewFile" :src="publicUrl(previewFile.storage_path)" controls autoplay />
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.file-thumb, .video-thumb { width: 42px; height: 42px; border-radius: 4px; }
.video-thumb { display: grid; place-items: center; color: #fff; background: #3a423d; border: 0; cursor: pointer; }
.upload-icon { margin-bottom: 8px; font-size: 24px; }
.preview-stage { display: grid; min-height: 260px; max-height: 70vh; place-items: center; overflow: hidden; background: #171a18; border-radius: 6px; }
.preview-stage img, .preview-stage video { display: block; max-width: 100%; max-height: 70vh; object-fit: contain; }
</style>

