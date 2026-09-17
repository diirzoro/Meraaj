let reactHooks = null;
try {
  // eslint-disable-next-line global-require
  reactHooks = require("eslint-plugin-react-hooks");
} catch {
  reactHooks = null;
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
  { ignores: ["build/**", "node_modules/**", "android/**", "plugins/**"] },
  base,
];
