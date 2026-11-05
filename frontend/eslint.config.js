import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage", "node_modules", "playwright-report", "test-results"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  reactHooks.configs.flat.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
  {
    // The overview ships in the main bundle; the readings barrel re-exports ECharts-based charts
    // that must stay in the lazily loaded detail chunk.
    files: ["src/features/tanks/TanksOverviewPage.tsx", "src/features/tanks/components/**"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              regex: "^\\.\\./(\\.\\./)?readings$",
              message: "Import readings modules directly; the barrel pulls ECharts into the main bundle.",
            },
          ],
        },
      ],
    },
  },
);
