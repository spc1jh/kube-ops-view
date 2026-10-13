const js = require('@eslint/js')
const globals = require('globals')

module.exports = [
    {ignores: ['src/vendor/**']},
    js.configs.recommended,
    {
        languageOptions: {
            sourceType: 'module',
            globals: {...globals.browser}
        },
        rules: {
            'indent': ['error', 4],
            'linebreak-style': ['error', 'unix'],
            'quotes': ['error', 'single'],
            'prefer-const': 'error',
            'no-redeclare': 'error',
            'no-unused-vars': ['warn', {argsIgnorePattern: '^_'}],
            'semi': ['error', 'never']
        }
    }
]
