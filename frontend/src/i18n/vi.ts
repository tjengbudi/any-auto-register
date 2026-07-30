import type { Catalog } from './zh'

/* 结构占位：本次发布不提供越南语翻译，所有值留空，由 LanguageContext 在构建期回退到中文。 */
const catalogViRaw: Catalog = {
  nav: {
    total: '',
    history: '',
    accounts: '',
    settings: '',
    settingsGeneral: '',
    settingsRegister: '',
    settingsMailbox: '',
    settingsCaptcha: '',
    settingsSms: '',
    settingsProxies: '',
    settingsChatgpt: '',
    settingsAdvanced: '',
    settingsAbout: '',
    themeSwitchToDark: '',
    themeSwitchToLight: '',
    themeFollowSystem: '',
    themeLight: '',
    themeDark: '',
    themeSystem: '',
    expandSidebar: '',
    collapseSidebar: '',
  },
  login: {
    loading: '',
    prompt: '',
    passwordPlaceholder: '',
    wrongPassword: '',
    requestFailed: '',
    verifying: '',
    submit: '',
  },
  settings: {
    languageGroupTitle: '',
    languageGroupDesc: '',
    languageRowLabel: '',
  },
}

export { catalogViRaw }
