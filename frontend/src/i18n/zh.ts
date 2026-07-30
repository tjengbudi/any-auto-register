/* 源语言目录（中文）。其余目录以此为基准类型，缺键或多键在 tsc -b 阶段报错。 */
const catalogZh = {
  nav: {
    total: '总览',
    history: '任务',
    accounts: '账号',
    settings: '设置',
    settingsGeneral: '通用',
    settingsRegister: '注册策略',
    settingsMailbox: '邮箱服务',
    settingsCaptcha: '验证服务',
    settingsSms: '接码服务',
    settingsProxies: '代理资源',
    settingsChatgpt: 'ChatGPT',
    settingsAdvanced: '高级',
    settingsAbout: '关于',
    themeSwitchToDark: '切换到深色',
    themeSwitchToLight: '切换到浅色',
    themeFollowSystem: '跟随系统',
    themeLight: '浅色',
    themeDark: '深色',
    themeSystem: '系统',
    expandSidebar: '展开侧栏',
    collapseSidebar: '收起侧栏',
  },
  login: {
    loading: '加载中...',
    prompt: '请输入访问密码',
    passwordPlaceholder: '密码',
    wrongPassword: '密码错误',
    requestFailed: '请求失败',
    verifying: '验证中...',
    submit: '登 录',
  },
  settings: {
    languageGroupTitle: '界面语言',
    languageGroupDesc: '选择应用的显示语言，切换后立即生效。',
    languageRowLabel: '显示语言',
  },
}

export type Catalog = typeof catalogZh
export { catalogZh }
