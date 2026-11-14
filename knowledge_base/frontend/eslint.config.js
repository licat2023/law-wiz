import js from '@eslint/js'
import prettier from 'eslint-config-prettier'
import vue from 'eslint-plugin-vue'
import ts from 'typescript-eslint'

export default [
  { ignores: ['dist/**', 'node_modules/**', '.data/**'] },
  js.configs.recommended,
  ...ts.configs.recommended,
  ...vue.configs['flat/recommended'],
  { files: ['**/*.vue'], languageOptions: { parserOptions: { parser: ts.parser } } },
  { files: ['src/**'], rules: { 'no-undef': 'off' } },
  prettier,
]
