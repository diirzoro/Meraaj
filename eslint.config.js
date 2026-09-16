const js = require("/app/frontend/node_modules/@eslint/js");
const reactHooks = require("/app/frontend/node_modules/eslint-plugin-react-hooks");

module.exports = [
  {
    ignores: [
      "**/node_modules/**",
      "**/build/**",
      "frontend/android/**",
      "frontend/plugins/**",
    ],
  },
  {
    files: ["**/*.{js,jsx}"],
    plugins: { "react-hooks": reactHooks },
    linterOptions: { reportUnusedDisableDirectives: false },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      ...js.configs.recommended.rules,
      "no-unused-vars": "off",
      "no-undef": "off",
      "no-empty": "off",
      "react-hooks/exhaustive-deps": "off",
      "react-hooks/rules-of-hooks": "off",
    },
  },
];
