let reactHooks = null;
for (const id of ["eslint-plugin-react-hooks", "/app/frontend/node_modules/eslint-plugin-react-hooks"]) {
  try {
    // eslint-disable-next-line global-require
    reactHooks = require(id);
    break;
  } catch {
    reactHooks = null;
  }
}

const base = {
  files: ["**/*.{js,jsx,mjs,cjs}"],
  linterOptions: { reportUnusedDisableDirectives: false },
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: "module",
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
  rules: {},
};

if (reactHooks) {
  base.plugins = { "react-hooks": reactHooks };
  base.rules = { "react-hooks/exhaustive-deps": "off", "react-hooks/rules-of-hooks": "off" };
}

module.exports = [
  { ignores: ["**/node_modules/**", "**/build/**", "frontend/android/**", "frontend/plugins/**"] },
  base,
];
