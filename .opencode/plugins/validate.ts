import type { Plugin } from "@opencode-ai/plugin";

const ValidatePlugin: Plugin = async (input) => {
  return {
    "tool.execute.after": async (ctx, output) => {
      if (ctx.tool !== "write" && ctx.tool !== "edit") return;

      const filePath = ctx.args?.file_path ?? ctx.args?.filePath ?? ctx.args?.filepath;
      if (!filePath) return;
      if (typeof filePath !== "string") return;
      if (!filePath.includes("knowledge/articles/") || !filePath.endsWith(".json")) return;

      try {
        await input.$`python3 hooks/validate_json.py ${filePath}`.nothrow();
      } catch {
        // silently ignore shell execution errors to avoid blocking the agent
      }
    },
  };
};

export default ValidatePlugin;
