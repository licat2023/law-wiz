// ESLint 扁平配置（ESLint 9 起 `--ext` 已移除，配置本身即范围声明）。
//
// 与 Prettier 的分工：ESLint 管**规则**（未使用变量、类型误用等），
// Prettier 管**排版**。两者职责重叠的规则由 eslint-config-prettier 关闭，
// 避免同一件事被两套工具给出互相矛盾的判断。
import js from '@eslint/js'
import prettier from 'eslint-config-prettier'
import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

export default [
  {
    // 生成物不参与检查：auto-imports.d.ts / components.d.ts 由
    // unplugin-* 在构建时生成，手改无效。
    ignores: ['dist/**', 'node_modules/**', 'auto-imports.d.ts', 'components.d.ts'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: {
      // .vue 里的 <script lang="ts"> 需要 TS 解析器接管
      parserOptions: { parser: tseslint.parser },
    },
    rules: {
      // TS 已检查未声明变量；no-undef 不认识 DOM 全局（HTMLElement、URL 等）
      'no-undef': 'off',
    },
  },
  prettier,

  {
    languageOptions: {
      globals: {
        window: 'readonly',
        document: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        localStorage: 'readonly',
        File: 'readonly',
        FormData: 'readonly',
        URL: 'readonly',
        Blob: 'readonly',
      },
    },
  },
]
