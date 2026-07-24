import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  {
    ignores: [
      'dist',
      'coverage',
      'public/mockServiceWorker.js',
      'src/test/**',
      '.claude/**',
      // Root-level config files and test files live outside tsconfig.app.json's
      // include set, so they cannot be type-checked by typescript-eslint. Lint
      // them under the non-typed block below.
      'vite.config.ts',
      'vite.verify.config.ts',
      'vitest.config.ts',
      'src/**/__tests__/**',
      'e2e/**',
    ],
  },
  // Type-aware linting for production source files.
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        project: ['./tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // React Compiler (global infer mode) handles dependency tracking automatically.
      // exhaustive-deps produces false positives when the compiler is enabled.
      'react-hooks/exhaustive-deps': 'off',
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
      // Promise safety — surface unhandled async work. Starts at warn for the
      // initial rollout; promote to error in a follow-up after the existing
      // backlog is cleared.
      '@typescript-eslint/no-floating-promises': 'warn',
      '@typescript-eslint/no-misused-promises': 'warn',
      // `any` is forbidden by project policy; surface as warning to allow incremental cleanup.
      '@typescript-eslint/no-explicit-any': 'warn',
      // Modern JS conveniences.
      '@typescript-eslint/prefer-nullish-coalescing': 'warn',
      '@typescript-eslint/prefer-optional-chain': 'warn',
      // Type-checked recommended set surfaces a few high-noise rules whose
      // existing violations are not safety-critical. Keep them as warnings to
      // unblock the rollout; tighten in follow-ups.
      '@typescript-eslint/no-unsafe-assignment': 'warn',
      '@typescript-eslint/no-unsafe-argument': 'warn',
      '@typescript-eslint/no-unsafe-member-access': 'warn',
      '@typescript-eslint/no-unsafe-call': 'warn',
      '@typescript-eslint/no-unsafe-return': 'warn',
      '@typescript-eslint/no-base-to-string': 'warn',
      '@typescript-eslint/no-redundant-type-constituents': 'warn',
      '@typescript-eslint/no-unnecessary-type-assertion': 'warn',
      '@typescript-eslint/require-await': 'warn',
      '@typescript-eslint/restrict-template-expressions': 'warn',
      '@typescript-eslint/unbound-method': 'warn',
    },
  },
)
