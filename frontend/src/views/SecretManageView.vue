<script setup lang="ts">
import { Delete, Edit, Key, Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onActivated, reactive, ref } from 'vue'

import { errorMessage, modelConfigsApi, secretsApi } from '@/api'
import type { ApiSecret, ModelConfig } from '@/types'

const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const items = ref<ApiSecret[]>([])
const configs = ref<ModelConfig[]>([])
const keyword = ref('')

const form = reactive({
  name: '',
  provider: '',
  description: '',
  secret_ref: '',
  value: '',
  status: 'ENABLED' as ApiSecret['status'],
})

/** 按关键字过滤（引用名 / 名称 / 厂商） */
const filtered = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return items.value
  return items.value.filter((item) =>
    [item.name, item.secret_ref, item.provider].some((field) => (field || '').toLowerCase().includes(key)),
  )
})

/** 每个密钥被多少条模型配置引用 */
const refCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const config of configs.value) {
    if (config.secret_ref) counts.set(config.secret_ref, (counts.get(config.secret_ref) ?? 0) + 1)
  }
  return counts
})

async function loadData() {
  loading.value = true
  try {
    const [secretList, configList] = await Promise.all([
      secretsApi.list(),
      modelConfigsApi.listAll(),
    ])
    items.value = secretList
    configs.value = configList
  } catch (error) {
    ElMessage.error(errorMessage(error, '密钥列表加载失败'))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', provider: '', description: '', secret_ref: '', value: '', status: 'ENABLED' })
  dialogVisible.value = true
}

function openEdit(item: ApiSecret) {
  editingId.value = item.id
  Object.assign(form, {
    name: item.name,
    provider: item.provider,
    description: item.description ?? '',
    secret_ref: item.secret_ref,
    value: '',
    status: item.status,
  })
  dialogVisible.value = true
}

async function save() {
  if (!form.secret_ref.trim()) return ElMessage.warning('请填写引用名')
  if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(form.secret_ref.trim())) {
    return ElMessage.warning('引用名只能包含字母、数字和下划线，且以字母开头')
  }
  if (!editingId.value && !form.value.trim()) return ElMessage.warning('请填写密钥内容')
  saving.value = true
  try {
    await secretsApi.save({
      id: editingId.value,
      name: form.name.trim() || form.secret_ref.trim(),
      provider: form.provider.trim(),
      description: form.description.trim() || null,
      secret_ref: form.secret_ref.trim(),
      value: form.value.trim() || null,
      status: form.status,
    })
    ElMessage.success(editingId.value ? '密钥已更新' : '密钥已保存')
    dialogVisible.value = false
    await loadData()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function remove(item: ApiSecret) {
  try {
    await ElMessageBox.confirm(
      `确定删除密钥「${item.name}」吗？删除后引用它的模型将无法调用接口。`,
      '删除密钥',
      { type: 'warning' },
    )
    const result = await secretsApi.remove(item.id)
    ElMessage.success(result.message || '密钥已删除')
    await loadData()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(errorMessage(error))
  }
}

onActivated(loadData)
</script>

<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1>密钥管理</h1>
        <p>集中维护各模型厂商的 API Key。密钥加密后存入数据库，页面只能看到掩码，明文不会回传浏览器。</p>
      </div>
      <div class="page-actions">
        <el-button type="primary" :icon="Plus" @click="openCreate">新增密钥</el-button>
      </div>
    </div>

    <el-alert
      class="hint"
      type="info"
      show-icon
      :closable="false"
      title="密钥以密文形式保存在 Supabase 数据库中，仅在 Edge Function 调用模型时解密使用。"
      description="在“模型管理”里把「密钥」一栏选中这里的引用名，即可让该模型配置使用对应密钥。"
    />

    <div class="filter-bar">
      <el-input
        v-model="keyword"
        clearable
        placeholder="搜索名称、引用名或厂商"
        style="width: 260px"
        :prefix-icon="Search"
      />
    </div>

    <section class="content-panel table-panel">
      <el-table v-loading="loading" :data="filtered" empty-text="暂无密钥，点击右上角新增">
        <el-table-column label="名称" min-width="180">
          <template #default="{ row }">
            <span class="secret-name"><el-icon><Key /></el-icon>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="provider" label="厂商" min-width="140">
          <template #default="{ row }"><span :class="{ muted: !row.provider }">{{ row.provider || '未填写' }}</span></template>
        </el-table-column>
        <el-table-column label="引用名" min-width="180" show-overflow-tooltip>
          <template #default="{ row }"><code class="mono-inline">{{ row.secret_ref }}</code></template>
        </el-table-column>
        <el-table-column label="密钥" min-width="160">
          <template #default="{ row }"><code class="mono-inline masked">{{ row.masked || '——' }}</code></template>
        </el-table-column>
        <el-table-column label="被引用" width="100">
          <template #default="{ row }">
            <el-tag v-if="refCounts.get(row.secret_ref)" size="small" type="warning" effect="plain">
              {{ refCounts.get(row.secret_ref) }} 个配置
            </el-tag>
            <span v-else class="muted">未引用</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'" effect="plain">
              {{ row.status === 'ENABLED' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button text :icon="Edit" @click="openEdit(row)">编辑</el-button>
            <el-button text type="danger" :icon="Delete" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑密钥' : '新增密钥'"
      width="min(600px, calc(100vw - 32px))"
    >
      <el-form label-position="top">
        <div class="form-grid">
          <el-form-item label="名称" required>
            <el-input v-model="form.name" placeholder="例如 OpenAI 主账号" />
          </el-form-item>
          <el-form-item label="厂商">
            <el-input v-model="form.provider" placeholder="例如 OpenAI / MiniMax / 火山方舟" />
          </el-form-item>
        </div>
        <el-form-item label="引用名" required>
          <el-input v-model="form.secret_ref" class="mono" placeholder="例如 OPENAI_API_KEY" />
          <div class="field-tip">模型配置通过这个引用名找到密钥，只能包含字母、数字和下划线。</div>
        </el-form-item>
        <el-form-item :label="editingId ? '密钥内容（留空则不修改）' : '密钥内容'" :required="!editingId">
          <el-input
            v-model="form.value"
            type="password"
            show-password
            class="mono"
            :placeholder="editingId ? '留空表示保留原密钥' : '粘贴厂商提供的 API Key'"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选，记录用途或额度信息" />
        </el-form-item>
        <el-form-item label="状态">
          <el-segmented
            v-model="form.status"
            :options="[{ label: '启用', value: 'ENABLED' }, { label: '停用', value: 'DISABLED' }]"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.hint { margin-bottom: 14px; }
.secret-name { display: inline-flex; align-items: center; gap: 6px; }
.secret-name .el-icon { color: #bf7025; }
.mono-inline { padding: 1px 6px; background: #f2f5f3; border-radius: 4px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.masked { color: #6a716c; }
.field-tip { margin-top: 4px; color: #8a918c; font-size: 12px; line-height: 1.5; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 620px) { .form-grid { grid-template-columns: 1fr; gap: 0; } }
</style>
