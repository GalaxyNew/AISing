<template>
  <main v-if="!token" class="login-page">
    <section class="login-card">
      <div>
        <p class="eyebrow">AI Sing Console</p>
        <h1>商业管理后台</h1>
        <p class="muted">用户、积分、客服和产品规则统一管理。</p>
      </div>
      <el-input v-model="loginForm.username" placeholder="管理员账号" size="large" />
      <el-input v-model="loginForm.password" placeholder="管理员密码" size="large" show-password @keyup.enter="login" />
      <el-button type="primary" size="large" @click="login">登录后台</el-button>
      <p class="hint">默认账号：admin / xxxx，首次登录后请修改密码。</p>
    </section>
  </main>

  <main v-else class="admin-layout">
    <aside class="sidebar">
      <div class="brand">
        <p class="eyebrow">AI Sing</p>
        <h2>商业管理</h2>
      </div>
      <el-menu class="side-menu" :default-active="tab" @select="tab = $event">
        <el-menu-item index="users">用户管理</el-menu-item>
        <el-menu-item index="support">客服与价格</el-menu-item>
        <el-menu-item index="records">积分记录</el-menu-item>
        <el-menu-item index="password">修改密码</el-menu-item>
      </el-menu>
      <el-button class="logout" @click="logout">退出登录</el-button>
    </aside>

    <section class="content">
      <header class="page-head">
        <div>
          <p class="eyebrow">Admin Console</p>
          <h1>{{ pageTitle }}</h1>
        </div>
        <el-button v-if="tab === 'users'" type="primary" @click="openCreateUser">新建用户</el-button>
      </header>

      <section v-if="tab === 'users'" class="panel">
        <div class="stat-grid">
          <div class="stat-card">
            <span>用户数量</span>
            <strong>{{ users.length }}</strong>
          </div>
          <div class="stat-card">
            <span>账户总积分</span>
            <strong>{{ totalCredits }}</strong>
          </div>
          <div class="stat-card">
            <span>当前规则</span>
            <strong>干声 {{ config.voice_train_cost }} / 歌曲 {{ config.song_process_cost }}</strong>
          </div>
        </div>
        <div class="toolbar">
          <el-input v-model="phone" placeholder="输入手机号搜索用户" clearable @keyup.enter="loadUsers" />
          <el-button @click="loadUsers">搜索</el-button>
        </div>
        <el-table :data="users" border stripe>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="username" label="用户名" />
          <el-table-column prop="phone" label="手机号" />
          <el-table-column prop="credits" label="训练积分" width="110" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="300">
            <template #default="{ row }">
              <el-button size="small" @click="openEditUser(row)">编辑</el-button>
              <el-button size="small" @click="resetPassword(row)">重置密码</el-button>
              <el-button size="small" type="primary" @click="addCredits(row)">加积分</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section v-if="tab === 'support'" class="two-column">
        <el-form label-width="140px" class="panel form-panel support-card">
          <div class="section-head">
            <div>
              <p class="eyebrow">Support</p>
              <h3>客服信息</h3>
            </div>
          </div>
          <div class="qr-preview">
            <span v-if="!support.qr_code_url">二维码预览</span>
            <img v-else :src="support.qr_code_url" alt="客服二维码" />
          </div>
          <el-form-item label="客服名称"><el-input v-model="support.name" /></el-form-item>
          <el-form-item label="二维码地址"><el-input v-model="support.qr_code_url" /></el-form-item>
          <el-form-item label="二维码上传">
            <el-upload :http-request="uploadQr" :show-file-list="false">
              <el-button>上传二维码</el-button>
            </el-upload>
          </el-form-item>
          <el-button type="primary" @click="saveSupport">保存客服信息</el-button>
        </el-form>

        <el-form label-width="150px" class="panel form-panel">
          <div class="section-head">
            <div>
              <p class="eyebrow">Pricing</p>
              <h3>积分价格与消耗</h3>
            </div>
          </div>
          <div class="rule-strip">
            <span>1积分 = {{ config.recharge_price_per_credit }}元</span>
            <span>干声 {{ config.voice_train_cost }}积分</span>
            <span>歌曲 {{ config.song_process_cost }}积分</span>
          </div>
          <el-form-item label="注册送积分"><el-input-number v-model="config.signup_bonus_credits" :min="0" /></el-form-item>
          <el-form-item label="干声训练消耗"><el-input-number v-model="config.voice_train_cost" :min="0" /></el-form-item>
          <el-form-item label="歌曲处理消耗"><el-input-number v-model="config.song_process_cost" :min="0" /></el-form-item>
          <el-form-item label="每积分价格"><el-input-number v-model="config.recharge_price_per_credit" :min="0" /></el-form-item>
          <el-button type="primary" @click="saveSupport">保存价格配置</el-button>
        </el-form>
      </section>

      <section v-if="tab === 'records'" class="panel">
        <div class="stat-grid records-stats">
          <div class="stat-card">
            <span>记录数量</span>
            <strong>{{ records.length }}</strong>
          </div>
          <div class="stat-card">
            <span>充值合计</span>
            <strong>{{ rechargeTotal }}</strong>
          </div>
          <div class="stat-card">
            <span>消费合计</span>
            <strong>{{ consumeTotal }}</strong>
          </div>
        </div>
        <div class="toolbar">
          <el-select v-model="recordType" clearable placeholder="记录类型">
            <el-option label="充值记录" value="recharge" />
            <el-option label="消费记录" value="consume" />
          </el-select>
          <el-button @click="loadRecords">刷新</el-button>
        </div>
        <el-table :data="records" border stripe>
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="user_id" label="用户ID" width="100" />
          <el-table-column prop="type" label="类型" width="100" />
          <el-table-column prop="amount" label="积分变化" width="120" />
          <el-table-column prop="balance_after" label="余额" width="100" />
          <el-table-column prop="note" label="备注" />
          <el-table-column prop="created_at" label="时间" />
        </el-table>
      </section>

      <section v-if="tab === 'password'" class="panel narrow">
        <el-form label-width="120px">
          <el-form-item label="旧密码"><el-input v-model="passwordForm.old_password" show-password /></el-form-item>
          <el-form-item label="新密码"><el-input v-model="passwordForm.new_password" show-password /></el-form-item>
          <el-button type="primary" @click="changePassword">修改密码</el-button>
        </el-form>
      </section>
    </section>

    <el-dialog v-model="userDialog.visible" :title="userDialog.mode === 'create' ? '新建用户' : '编辑用户'" width="520px">
      <el-form label-width="110px">
        <p class="dialog-note">创建账号后，用户可使用客户端登录。初始积分默认读取当前产品配置，也可以手动调整。</p>
        <el-form-item label="用户名">
          <el-input v-model="userForm.username" :disabled="userDialog.mode === 'edit'" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item v-if="userDialog.mode === 'create'" label="登录密码">
          <el-input v-model="userForm.password" show-password placeholder="请输入初始密码" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="userForm.phone" placeholder="请输入手机号" />
        </el-form-item>
        <el-form-item label="训练积分">
          <el-input-number v-model="userForm.credits" :min="0" />
        </el-form-item>
        <el-form-item v-if="userDialog.mode === 'edit'" label="状态">
          <el-select v-model="userForm.status">
            <el-option label="active" value="active" />
            <el-option label="disabled" value="disabled" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="submitUserDialog">保存</el-button>
      </template>
    </el-dialog>
  </main>
</template>

<script setup>
import axios from 'axios'
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || 'https://xxxx/sing-api' })
const token = ref(localStorage.getItem('admin_token') || '')
const tab = ref('users')
const phone = ref('')
const users = ref([])
const records = ref([])
const recordType = ref('')
const loginForm = reactive({ username: 'admin', password: 'xxxx' })
const passwordForm = reactive({ old_password: '', new_password: '' })
const config = reactive({ signup_bonus_credits: 480, voice_train_cost: 450, song_process_cost: 1, recharge_price_per_credit: 1 })
const support = reactive({ name: '', qr_code_url: '' })
const userDialog = reactive({ visible: false, mode: 'create', userId: null })
const userForm = reactive({ username: '', password: '', phone: '', credits: 480, status: 'active' })

const pageTitle = computed(() => ({
  users: '用户管理',
  support: '客服与价格',
  records: '积分记录',
  password: '修改密码'
}[tab.value]))
const totalCredits = computed(() => users.value.reduce((sum, user) => sum + Number(user.credits || 0), 0))
const rechargeTotal = computed(() => records.value.filter(row => row.type === 'recharge').reduce((sum, row) => sum + Number(row.amount || 0), 0))
const consumeTotal = computed(() => Math.abs(records.value.filter(row => row.type === 'consume').reduce((sum, row) => sum + Number(row.amount || 0), 0)))

api.interceptors.request.use((request) => {
  if (token.value) request.headers.Authorization = `Bearer ${token.value}`
  return request
})

async function login() {
  try {
    const { data } = await api.post('/api/admin/login', loginForm)
    token.value = data.token
    localStorage.setItem('admin_token', token.value)
    await Promise.all([loadUsers(), loadSupport(), loadRecords()])
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '账号或密码错误')
  }
}
function logout() {
  token.value = ''
  localStorage.removeItem('admin_token')
}
async function loadUsers() {
  users.value = (await api.get('/api/admin/users', { params: { phone: phone.value } })).data
}
function openCreateUser() {
  Object.assign(userForm, { username: '', password: '', phone: '', credits: config.signup_bonus_credits || 480, status: 'active' })
  Object.assign(userDialog, { visible: true, mode: 'create', userId: null })
}
function openEditUser(row) {
  Object.assign(userForm, { username: row.username, password: '', phone: row.phone, credits: row.credits, status: row.status })
  Object.assign(userDialog, { visible: true, mode: 'edit', userId: row.id })
}
async function submitUserDialog() {
  if (userDialog.mode === 'create') {
    await api.post('/api/admin/users', {
      username: userForm.username,
      password: userForm.password,
      phone: userForm.phone,
      credits: userForm.credits
    })
    ElMessage.success('用户已创建')
  } else {
    await api.put(`/api/admin/users/${userDialog.userId}`, {
      phone: userForm.phone,
      credits: userForm.credits,
      status: userForm.status
    })
    ElMessage.success('用户已保存')
  }
  userDialog.visible = false
  loadUsers()
}
async function resetPassword(row) {
  const password = await ElMessageBox.prompt('新密码', `重置 ${row.username} 的密码`)
  await api.post(`/api/admin/users/${row.id}/reset-password`, { password: password.value })
  ElMessage.success('已重置')
}
async function addCredits(row) {
  const amount = await ElMessageBox.prompt('增加积分', `给 ${row.username} 充值`)
  await api.post(`/api/admin/users/${row.id}/credits`, { amount: Number(amount.value), note: '后台充值' })
  loadUsers()
}
async function loadSupport() {
  Object.assign(config, (await api.get('/api/admin/config')).data)
  Object.assign(support, (await api.get('/api/admin/support')).data)
}
async function saveSupport() {
  await api.put('/api/admin/config', config)
  await api.put('/api/admin/support', support)
  ElMessage.success('已保存')
}
async function uploadQr(options) {
  try {
    const file = options.file
    const contentType = file.type || 'application/octet-stream'
    const { data } = await api.post('/api/admin/oss/presign-upload', {
      category: 'support_qr',
      filename: file.name,
      content_type: contentType
    })
    await axios.put(data.upload_url, file, { headers: data.headers || { 'Content-Type': contentType } })
    support.qr_code_url = data.public_url
    await api.put('/api/admin/support', support)
    options.onSuccess?.(data)
    ElMessage.success('二维码已上传')
  } catch (error) {
    options.onError?.(error)
    ElMessage.error('二维码上传失败')
  }
}
async function loadRecords() {
  records.value = (await api.get('/api/admin/credit-transactions', { params: { transaction_type: recordType.value } })).data
}
async function changePassword() {
  await api.post('/api/admin/password', passwordForm)
  ElMessage.success('密码已修改，请重新登录')
  logout()
}

onMounted(() => {
  if (token.value) Promise.all([loadUsers(), loadSupport(), loadRecords()])
})
</script>
